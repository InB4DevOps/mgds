import hashlib
import json
import math
from typing import Any

from tqdm import tqdm

from mgds.PipelineModule import PipelineModule
from mgds.pipelineModuleTypes.SingleVariationRandomAccessPipelineModule import SingleVariationRandomAccessPipelineModule


class RamCache(
    PipelineModule,
    SingleVariationRandomAccessPipelineModule,
):
    def __init__(
            self,
            cache_names: list[str],
            sort_names: list[str] | None = None,
            repeats_in_name: str | None = None,
            variations_group_in_name: str | list[str] | None = None,
    ):
        super(RamCache, self).__init__()

        self.cache_names = cache_names
        self.sort_names = [] if sort_names is None else sort_names

        self.repeats_in_name = repeats_in_name
        self.variations_group_in_name = \
            [variations_group_in_name] if isinstance(variations_group_in_name, str) else variations_group_in_name

        self.cache = None
        self.variations_initialized = False

    def length(self) -> int:
        if not self.variations_initialized:
            return self._get_previous_length(self.cache_names[0])
        else:
            return sum(x for x in self.group_output_samples.values())

    def get_inputs(self) -> list[str]:
        return self.sort_names + self.sort_names

    def get_outputs(self) -> list[str]:
        return self.sort_names + self.sort_names

    def __string_key(self, data: list[Any]) -> str:
        json_data = json.dumps(data, sort_keys=True, ensure_ascii=True, separators=(',', ':'), indent=None)
        return hashlib.sha256(json_data.encode('utf-8')).hexdigest()

    def __init_variations(self):
        """
        Prepares variations before caching starts. Each index is sorted into a group.

        Data is written into three variables.
            self.group_variations, mapping group keys to the number of variations of that group
            self.group_indices, mapping group keys to a list of input indices contained in the group
            self.group_output_samples, mapping group keys to the number of indices in the cache output for each group
        """
        if self.repeats_in_name is not None:
            group_indices = {}
            group_repeats = {}

            for in_index in range(self._get_previous_length(self.repeats_in_name)):
                repeats = self._get_previous_item(0, self.repeats_in_name, in_index)
                group_key = self.__string_key(
                    [self._get_previous_item(0, name, in_index) for name in self.variations_group_in_name]
                )

                if group_key not in group_indices:
                    group_indices[group_key] = []
                if group_key not in group_repeats:
                    group_repeats[group_key] = repeats
                group_indices[group_key].append(in_index)

            group_output_samples = {}
            for group_key, repeats in group_repeats.items():
                num = int(math.floor(len(group_indices[group_key]) * repeats))
                group_output_samples[group_key] = num
        else:
            first_previous_name = self.cache_names[0] if len(self.cache_names) > 0 else self.cache_names[0]

            group_indices = {'': [in_index for in_index in range(self._get_previous_length(first_previous_name))]}
            group_output_samples = {'': len(group_indices[''])}

        self.aggregate_cache = {}

        self.group_indices = group_indices
        self.group_output_samples = group_output_samples

        self.variations_initialized = True

    def __get_input_index(self, out_variation: int, out_index: int) -> (str, int, int):
        offset = 0
        for group_key, group_output_samples in self.group_output_samples.items():
            if out_index >= group_output_samples + offset:
                offset += group_output_samples
                continue

            local_index = (out_index - offset) + (out_variation * self.group_output_samples[group_key])
            in_variation = (local_index // len(self.group_indices[group_key]))
            group_index = local_index % len(self.group_indices[group_key])
            in_index = self.group_indices[group_key][group_index]

            return group_key, in_variation, group_index, in_index

    def start(self, variation: int):
        if not self.variations_initialized:
            self.__init_variations()

        self.cache = []
        length = sum(x for x in self.group_output_samples.values())
        for index in tqdm(range(length), desc='caching'):
            if index % 100 == 0:
                self._torch_gc()

            group_key, in_variation, group_index, in_index = self.__get_input_index(self.current_variation, index)

            item = {}

            for name in self.cache_names:
                item[name] = self._get_previous_item(in_variation, name, in_index)

            self.cache.append(item)

    def get_item(self, index: int, requested_name: str = None) -> dict:
        if requested_name in self.cache_names:
            return self.cache[index]
        elif requested_name in self.sort_names:
            group_key, in_variation, group_index, in_index = self.__get_input_index(self.current_variation, index)
            value = self._get_previous_item(self.current_variation, requested_name, in_index)
            return {
                requested_name: value
            }
