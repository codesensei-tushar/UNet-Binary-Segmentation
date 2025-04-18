from sklearn.model_selection import train_test_split
import glob
import os
import numpy as np
import torch
import albumentations as A
import cv2

from utils import get_label_mask, set_class_values
from torch.utils.data import Dataset, DataLoader

def get_images(config):
    """
    Load images and masks from a single folder and split into training and validation sets.
    
    :param root_path: Path to the main dataset folder containing "images" and "masks" subfolders.
    :param test_size: Proportion of data to allocate to validation set (default: 20%).
    :param random_state: Random seed for reproducibility.
    """
    image_dir = config["human-segmentation"]["image_dir"]  # Path to images directory
    mask_dir = config["human-segmentation"]["mask_dir"]    # Path to masks directory

    # List all images and masks from the directories
    images = sorted([os.path.join(image_dir, img) for img in os.listdir(image_dir)])
    masks = sorted([os.path.join(mask_dir, mask) for mask in os.listdir(mask_dir)])

    # Perform an 80-20 train-validation split
    train_images, valid_images, train_masks, valid_masks = train_test_split(
        images, masks, test_size=0.2, random_state=42
    )

    return train_images, train_masks, valid_images, valid_masks

def train_transforms(img_size):
    """
    Transforms/augmentations for training images and masks.

    :param img_size: Integer, for image resize.
    """
    train_image_transform = A.Compose([
        A.Resize(img_size, img_size, always_apply=True),
        A.HorizontalFlip(p=0.5),
        A.RandomBrightnessContrast(p=0.2),
        A.RandomSunFlare(p=0.2),
        A.RandomFog(p=0.2),
        A.Rotate(limit=25),
    ], additional_targets={"mask": "mask"})
    return train_image_transform

def valid_transforms(img_size):
    """
    Transforms/augmentations for validation images and masks.

    :param img_size: Integer, for image resize.
    """
    valid_image_transform = A.Compose([
        A.Resize(img_size, img_size, always_apply=True),
    ], additional_targets={"mask": "mask"})
    return valid_image_transform

class SegmentationDataset(Dataset):
    def __init__(
        self, 
        image_paths, 
        mask_paths, 
        tfms, 
        label_colors_list,
        classes_to_train,
        all_classes
    ):
        self.image_paths = image_paths
        self.mask_paths = mask_paths
        self.tfms = tfms
        self.label_colors_list = label_colors_list
        self.all_classes = all_classes
        self.classes_to_train = classes_to_train
        # Convert string names to class values for masks.
        self.class_values = set_class_values(
            self.all_classes, self.classes_to_train
        )

    def __len__(self):
        return len(self.image_paths)

    def __getitem__(self, index):
        image = cv2.imread(self.image_paths[index], cv2.IMREAD_COLOR)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB).astype('float32')
        image = image / 255.0
        mask = cv2.imread(self.mask_paths[index], cv2.IMREAD_COLOR)
        # mask = cv2.cvtColor(mask, cv2.COLOR_BGR2RGB).astype('float32')
        mask = cv2.resize(mask, (image.shape[1], image.shape[0]), interpolation=cv2.INTER_NEAREST)
        # Make all instances of person 255 pixel value and background 0.
        im = mask > 0
        mask[im] = 255
        mask[np.logical_not(im)] = 0

        # print(self.mask_paths[index])
        # cv2.imshow('Image', mask)
        # cv2.waitKey(0)

        transformed = self.tfms(image=image, mask=mask)
        image = transformed['image']
        mask = transformed['mask']
        
        # Get colored label mask.
        mask = get_label_mask(mask, self.class_values, self.label_colors_list)
       
        image = np.transpose(image, (2, 0, 1))
        
        image = torch.tensor(image, dtype=torch.float)
        mask = torch.tensor(mask, dtype=torch.long) 
        # print(f"Original Image Shape: {image.shape}")
        # print(f"Original Mask Shape: {mask.shape}")

        return image, mask

def get_dataset(
    train_image_paths, 
    train_mask_paths,
    valid_image_paths,
    valid_mask_paths,
    all_classes,
    classes_to_train,
    label_colors_list,
    img_size
):
    train_tfms = train_transforms(img_size)
    valid_tfms = valid_transforms(img_size)

    train_dataset = SegmentationDataset(
        train_image_paths,
        train_mask_paths,
        train_tfms,
        label_colors_list,
        classes_to_train,
        all_classes
    )
    valid_dataset = SegmentationDataset(
        valid_image_paths,
        valid_mask_paths,
        valid_tfms,
        label_colors_list,
        classes_to_train,
        all_classes
    )
    return train_dataset, valid_dataset

def get_data_loaders(train_dataset, valid_dataset, batch_size):
    train_data_loader = DataLoader(
        train_dataset, batch_size=batch_size, drop_last=False
    )
    valid_data_loader = DataLoader(
        valid_dataset, batch_size=batch_size, drop_last=False
    )

    return train_data_loader, valid_data_loader