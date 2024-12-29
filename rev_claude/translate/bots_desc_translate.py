from deep_translator import GoogleTranslator
from rev_claude.configs import POE_BOT_INFO, POE_BOT_INFO_ZH
from rev_claude.utils.json_utils import load_json, save_json
from copy import deepcopy
from loguru import logger
from tqdm import tqdm
import json
import re
import asyncio


class POEBotInfoTranslator:
    def __init__(self):
        self.data = load_json(POE_BOT_INFO)
        self.max_retries = 3
        self.delay_seconds = 1
        self.translator = GoogleTranslator(source="en", target="zh-CN")

    def is_eng_str(self, _str: str) -> bool:
        if not _str:
            return False
        _str = _str.replace(" ", "")
        str_size = len(_str)
        eng_char_pattern = re.compile(r"[a-zA-Z]")
        eng_char_count = len(eng_char_pattern.findall(_str))
        return eng_char_count / str_size > 0.8

    async def translate_helper(
        self, eng_str: str, model_name: str
    ) -> tuple[str, str, str]:
        for attempt in range(self.max_retries):
            try:
                translation = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self.translator.translate(eng_str)
                )

                if translation:
                    return model_name, eng_str, translation
                raise Exception("Translation failed - empty result")

            except Exception as e:
                logger.warning(
                    f"Translation attempt {attempt + 1} failed for {model_name}: {str(e)}"
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.delay_seconds)
                else:
                    logger.error(
                        f"Failed to translate after {self.max_retries} attempts: {eng_str}"
                    )
                    return model_name, eng_str, eng_str


async def main():
    translator = POEBotInfoTranslator()
    translated_data = deepcopy(translator.data)

    translation_tasks = []
    for model_name, model_info in translator.data.items():
        desc = model_info["desc"]
        if translator.is_eng_str(desc):
            translation_tasks.append(translator.translate_helper(desc, model_name))

    with tqdm(total=len(translation_tasks), desc="Translating") as pbar:

        async def update_progress(task):
            result = await task
            pbar.update(1)
            return result

        progress_tasks = [update_progress(task) for task in translation_tasks]
        results = await asyncio.gather(*progress_tasks)

    for model_name, orig_desc, trans_desc in results:
        logger.info(
            f"Model: {model_name}, Desc: {orig_desc}, Translation: {trans_desc}"
        )
        translated_data[model_name]["desc"] = trans_desc[:300]
        if "sd" in model_name or "stable" in model_name:
            translated_data[model_name]["text2image"] = True
            translated_data[model_name]["owned_by"] = "stabilityai"
        if "fal." in translated_data[model_name]["owned_by"]:
            translated_data[model_name]["text2image"] = True
        translated_data[model_name]["owned_by"] = (
            translated_data[model_name]["owned_by"]
            .replace("This bot is powered by ", "")
            .strip(".")
        )

    logger.debug(json.dumps(translated_data, indent=4))
    save_json(POE_BOT_INFO_ZH, translated_data)


if __name__ == "__main__":
    asyncio.run(main())
