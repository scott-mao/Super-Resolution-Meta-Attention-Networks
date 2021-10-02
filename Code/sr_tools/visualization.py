from skimage.io import imsave
import os
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
from PIL import Image
import math
import pandas as pd
from scipy.signal import savgol_filter

import SISR.configuration.constants as sconst
from sr_tools.image_manipulation import CenterCrop
from sr_tools.image_manipulation import ycbcr_convert


def extract_ims_from_gallery(gallery_ids, gallery_files, file_ids, im_dims,
                             gallery_im_loc=
                             os.path.join(sconst.data_directory,
                                          'celeba/png_samples/celeba_png_align/eval_vgg_features/gallery_0_images')):

    images = np.zeros((len(file_ids), 3, *im_dims), dtype=np.uint8)
    centre_cropper = CenterCrop(*im_dims)
    for index, id in enumerate(file_ids):
        images[index, :] = np.asarray(
            centre_cropper(Image.open(os.path.join(gallery_im_loc, gallery_files[list(gallery_ids).index(id)])))).transpose(
            (2, 0, 1))

    return images


def safe_image_save(images, out_loc, names, config, max_val=1, im_type='jpg'):
    """
    Saves given image to file.
    :param images: Batch of numpy images (either BxCxHxW or BxHxWxC).
    :param out_loc: output folder location.
    :param names: image save names.
    :param config: configuration of supplied image array.
    :param max_val: Input image maximum pixel value.
    :param im_type: specify jpg or png ycbcr conversion
    :return: None
    """
    # TODO: pre-processing won't work here if image is already a uint8
    for index in range(images.shape[0]):
        if config == 'ycbcr':
            im_rgb = ycbcr_convert(images[index, :], input=config, im_type=im_type)
        else:
            im_rgb = images[index, :]

        if im_rgb.shape[0] == 3:
            im_rgb = im_rgb.transpose([1, 2, 0])

        im_rgb = np.clip((im_rgb * 255/max_val), 0, 255).astype(np.uint8)

        imsave(os.path.join(out_loc, names[index]), im_rgb)


def index_converter(ind, images_per_row):
    return int(ind / images_per_row), ind % images_per_row  # converts indices to double


def prep_figure(rows, images_per_row, images_per_fig, double_indexing, figsize=(10, 10)):
    f, ax = plt.subplots(rows, images_per_row, figsize=figsize)  # prepare subplot axes TODO: find good figsize for various input image combinations
    for raw_ind in range(images_per_fig, rows*images_per_row):  # turning off unused slots
        if double_indexing:
            ind = index_converter(raw_ind, images_per_row)
        else:
            ind = raw_ind
        ax[ind].axis('off')
    return f, ax


def interpret_sisr_images(image_package, metrics, metric_names, out_loc, names, config='ycbcr', im_type='jpg',
                          max_val=1, direct_view=False, save_images=True, extra_info=None, images_per_row=4):
    """
    Lines up given images for direct comparison, and saves to file (if specified).
    :param image_package: dictionary containing images to compare.
    :param metrics: Metrics to print out to image titles.
    :param metric_names: Metric keys
    :param out_loc: Output directory.
    :param names: Image group names.
    :param config: Type of images (RGB or YCbCr).
    :param im_type: jpg or png image conversion.
    :param max_val: image maximum pixel value.
    :param direct_view: Enable for direct viewing in application of choice.
    :param save_images: Enable to save resulting comparison to file.
    :param extra_info: Any additional metadata to add to output.
    :param images_per_row: maximum number of images to place in a row.
    :return: None
    """

    ######## Figure Setup ########
    images_per_fig = len(image_package)
    rows = math.ceil(images_per_fig/images_per_row)
    # format required by matplotlib
    rect = None  # patch used to highlight parts of image

    if rows == 1:
        double_indexing = False
    else:
        double_indexing = True

    image_ordering = {'face_crop': (images_per_fig-2, 'Face Crop'),  # TODO: find a better way to hardcode these...
                      'Reference': (images_per_fig-1, 'Reference')}
    next_index = 0
    for keys in [('HR', 'Ground Truth'), ('LR', 'Low Res')]:
        if keys[0] in image_package:
            image_ordering[keys[0]] = (next_index, keys[1])
            next_index += 1

    for key in image_package:  # preparing information for image titles
        if key not in image_ordering:
            title = key
            if len(title) > 14:
                title = title[:int(len(title)/2)] + '\n' + title[int(len(title)/2):]
            if extra_info is not None:
                for line in extra_info[key]:
                    title += '\n%s %s' % (line[0], line[1])
            image_ordering[key] = (next_index, title)
            next_index += 1

    f, ax = prep_figure(rows, images_per_row, images_per_fig, double_indexing)

    ######## Figure Drawing ########
    for im_index, name in enumerate(names):
        for key, val in image_package.items():
            plot_ind, title = image_ordering[key]  # extract pre-set locations and titles
            if double_indexing:
                plot_ind = index_converter(plot_ind, images_per_row)

            if key == 'Reference' or key == 'HR':
                ax[plot_ind].imshow(val[im_index, :].transpose([1, 2, 0]))
                if key == 'HR' and 'VGG_FR_Rank' in metric_names:
                    label = 'VGG_Rank: {}'.format(int(metrics[key+'-'+'VGG_FR_Rank'][im_index]))
                else:
                    label = ''

            elif key == 'face_crop':
                ax[plot_ind].imshow(val[0][im_index, :].transpose([1, 2, 0]))
                bounds = val[1][im_index]
                if bounds is not None:
                    rect = patches.Rectangle((bounds['left'], bounds['top']),
                                             bounds['width'], bounds['height'], linewidth=1,
                                             edgecolor='r', fill=False)
                    ax[plot_ind].add_patch(rect)
                label = ''
            else:
                if key == 'LR':
                    im_rgb = (val[im_index, :] * 255/max_val).astype(np.int)
                else:
                    if config == 'ycbcr':  # convert image back to RGB if required
                        im_rgb = np.clip((ycbcr_convert(val[im_index, :], input='ycbcr',
                                                        im_type=im_type) * 255/max_val).astype(np.int), 0, 255)
                        # converts input and clips to valid range.  This is required due to network sometimes producing
                        # oversaturated pixels
                    else:
                        im_rgb = np.clip((val[im_index, :] * 255/max_val).astype(np.int), 0, 255)

                label = ''
                for m_name in metric_names:  # place metric information beneath relevant images
                    if m_name == 'VGG_FR_Rank':
                        label += '{}: {}\n'.format('VGG_Rank', int(metrics[key+'>'+m_name][im_index]))
                    else:
                        label += '{}: {:.3f}\n'.format(m_name, metrics[key+'>'+m_name][im_index])

                if im_rgb.shape[0] == 3:  # convert to HxWxC format for saving and viewing
                    im_rgb = im_rgb.transpose([1, 2, 0])

                ax[plot_ind].imshow(im_rgb)

            ax[plot_ind].set_xlabel(label, fontsize=13)
            ax[plot_ind].set_xticks([])
            ax[plot_ind].set_yticks([])
            ax[plot_ind].set_title(title, fontsize=16)

        plt.tight_layout()
        if save_images:
            # TODO: check if image name is a recursive (folder path) and then create folder if so
            plt.savefig(os.path.join(out_loc, name))
        if direct_view:
            plt.show()

        if rect is not None:
            rect.remove()  # removes any drawn rectangles
            rect = None
    plt.close(f)


def compare_training_curves(model_loc, out_name, models, metric='val-PSNR', epoch_range=None, psnr_range=None,
                            smooth=False):
    """
    Function that quickly prints out model validation PSNR in given epoch range.
    :param model_loc: Model base location.
    :param out_name: Output graph filename.
    :param models: List of models to include in graph (all models should either have their entire file path,
    or their experiment name only if they are located in the model_loc provided).
    :param metric: The metric to plot out in the graph.
    :param epoch_range:  Epoch range to cover in output plot.
    :param psnr_range:  Max/min PSNR range.
    :param smooth: Set to true to smooth out curves, making them more interpretable.
    :return:
    """

    f = plt.figure(figsize=(14, 6))
    for index, model in enumerate(models):
        if '/' in model:
            data = pd.read_csv(os.path.join(model, 'result_outputs/summary.csv'))
        else:
            data = pd.read_csv(os.path.join(model_loc, model, 'result_outputs/summary.csv'))

        if smooth:
            x_epoch = data['epoch']
            y_metric = savgol_filter(data[metric], 11, 3)
            # x_epoch = np.linspace(0, max(data['epoch']), max(data['epoch'])*5)
            # a_BSpline = interpolate.make_interp_spline(data['epoch'], data[metric],  k=2)
            # y_metric = a_BSpline(x_epoch)
        else:
            x_epoch = data['epoch']
            y_metric = data[metric]
        plt.plot(x_epoch, y_metric, label=model.split('/')[-1])
    if epoch_range is not None:
        plt.xlim(epoch_range[0], epoch_range[1])
    if psnr_range is not None:
        plt.ylim(psnr_range[0], psnr_range[1])

    font_setting = 20
    plt.xlabel('Epoch number', fontsize=font_setting)
    plt.ylabel('Validation PSNR', fontsize=font_setting)  # TODO: change this to reflect metric selected
    plt.xticks(fontsize=font_setting-5)
    plt.yticks(fontsize=font_setting-5)
    plt.tight_layout()
    plt.legend(loc='lower right', fontsize=font_setting-5)
    plt.savefig(out_name)
    plt.close(f)


