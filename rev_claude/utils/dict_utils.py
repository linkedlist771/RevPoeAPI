from typing import Dict


def remove_null_val_from_dict(original_dict: Dict) -> Dict:
    return {k: v for k, v in original_dict.items() if v}


def make_dict_handle_lower(original_dict: Dict) -> Dict:
    original_dict["handle"] = original_dict["handle"].lower()
    return original_dict
