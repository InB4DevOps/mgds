import torch
from PIL import Image
from transformers import DPTForDepthEstimation, DPTImageProcessor, CLIPTokenizer

from dataLoader.TrainDataSet import PipelineModule


class GenerateDepth(PipelineModule):
    def __init__(self, path_in_name: str, image_out_name: str, image_depth_processor: DPTImageProcessor, depth_estimator: DPTForDepthEstimation):
        super(GenerateDepth, self).__init__()
        self.path_in_name = path_in_name
        self.image_out_name = image_out_name
        self.image_depth_processor = image_depth_processor
        self.depth_estimator = depth_estimator

    def length(self) -> int:
        return self.get_previous_length(self.path_in_name)

    def get_inputs(self) -> list[str]:
        return [self.path_in_name]

    def get_outputs(self) -> list[str]:
        return [self.image_out_name]

    def get_item(self, index: int) -> dict:
        path = self.get_previous_item(self.path_in_name, index)

        image = Image.open(path)
        image = image.convert('RGB')

        with torch.no_grad():
            image = self.image_depth_processor(image, return_tensors="pt").pixel_values
            image = image.to(self.pipeline.device)
            depth = self.depth_estimator(image).predicted_depth

            depth_min = torch.amin(depth, dim=[1, 2], keepdim=True)
            depth_max = torch.amax(depth, dim=[1, 2], keepdim=True)
            depth = 2.0 * (depth - depth_min) / (depth_max - depth_min) - 1.0

        return {
            self.image_out_name: depth
        }


class GenerateMaskedConditioningImage(PipelineModule):
    def __init__(self, image_in_name: str, mask_in_name: str, image_out_name: str):
        super(GenerateMaskedConditioningImage, self).__init__()
        self.image_in_name = image_in_name
        self.mask_in_name = mask_in_name
        self.image_out_name = image_out_name

    def length(self) -> int:
        return self.get_previous_length(self.image_in_name)

    def get_inputs(self) -> list[str]:
        return [self.image_in_name, self.mask_in_name]

    def get_outputs(self) -> list[str]:
        return [self.image_out_name]

    def get_item(self, index: int) -> dict:
        image = self.get_previous_item(self.image_in_name, index)
        mask = self.get_previous_item(self.mask_in_name, index)

        conditioning_image = image * mask

        return {
            self.image_out_name: conditioning_image
        }


class Tokenize(PipelineModule):
    def __init__(self, in_name: str, out_name: str, tokenizer: CLIPTokenizer):
        super(Tokenize, self).__init__()
        self.in_name = in_name
        self.out_name = out_name
        self.tokenizer = tokenizer

    def length(self) -> int:
        return self.get_previous_length(self.in_name)

    def get_inputs(self) -> list[str]:
        return [self.in_name]

    def get_outputs(self) -> list[str]:
        return [self.out_name]

    def get_item(self, index: int) -> dict:
        text = self.get_previous_item(self.in_name, index)

        tokens = self.tokenizer(
            text,
            padding='max_length',
            truncation=True,
            max_length=self.tokenizer.model_max_length,
        ).input_ids

        return {
            self.out_name: tokens
        }
