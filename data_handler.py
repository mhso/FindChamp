import json
import os
from time import sleep

import requests

IMG_FILE_TYPE = "png"

IGNORED_SKINS = set([ # Hall of legends and other limited skins
    "ahri_85",
    "ahri_86",
    "kaisa_70",
    "kaisa_71",
    "riven_7",
])

SPECIAL_SKIN_CASES = {
    "ambessa_0": ["ambessa_circle_0.domina"],
    "ambessa_1": ["ambessa_circle_1.matcha_ambessa"],
    "anivia_0": ["cryophoenix_circle"],
    "anivia_0": ["cryophoenix_circle"],
    "blitzcrank_0": ["steamgolem_circle"],
    "chogath_0": ["greenterror_circle"],
    "elise_34": ["elise_circle_34.skins_elise_care_skin34"],
    "fiddlesticks_46": ["fiddlesticks_circle_skin_46.skins_fiddlesticks_skin34"],
    "leblanc": ["leblanc_circle_[num].leblanc_rework"],
    "lux_7": [
        "lux_circle_7_air",
        "lux_circle_7_dark",
        "lux_circle_7_fire",
        "lux_circle_7_ice",
        "lux_circle_7_light",
        "lux_circle_7_magma",
        "lux_circle_7_mystic",
        "lux_circle_7_nature",
        "lux_circle_7_storm",
        "lux_circle_7_water",
    ],
    "missfortune_16": [
        "missfortune_circle_16_royalarms",
        "missfortune_circle_16_scarletfair",
        "missfortune_circle_16_starswarm",
        "missfortune_circle_16_zerohour",
    ],
    "orianna_0": ["oriana_circle"], # Yep, there's a typo...
    "rammus_0": ["armordillo_circle"],
    "renata_31": ["renata_circle_31.skins_renata_care_skin31"],
    "samira_33": ["samira_circle_33.skins_samira_care_skin33"],
    "shaco_0": ["jester_circle"],
    "teemo": ["teemo_circle_[num].asu_teemo"],
    "viktor": ["viktor_circle_[num].viktorvgu"],
    "viktor_24": ["viktor_circle_24.skins_viktorrework_skin24"],
    "vladimir_48": ["vladimir_circle_48.skins_vladimir_care_skin48"],
    "warwick_56": ["warwick_circle_56.skins_warwick_skin56"],
    "xinzhao": ["xinzhaorework_circle_[num].xinzhaorework"],
    "xinzhao_47": ["xinzhao_circle_47.skins_xinzhaorework_skin47"],
    "xinzhao_2": ["xinzhao_circle_2.xinzhaorework"],
    "xinzhao_4": ["xinzhao_circle_4.xinzhaorework"],
    "zilean_0": ["chronokeeper_circle"],
}

class DataHandler:
    def __init__(self, patch: str | None = None):
        self.patch = patch or self.fetch_latest_patch()

        if os.path.exists("latest_data.json"):
            with open("latest_data.json", "r", encoding="utf-8") as fp:
                champ_data = json.load(fp)

            new_patch = champ_data["version"] != self.patch
        else:
            new_patch = True

        if new_patch:
            print(f"Our champ data is outdated, fetching data for patch {self.patch}...")
            champ_data = self.fetch_champ_data()
            missing_portraits = self.get_missing_portraits(champ_data)
            self.fetch_all_portraits(missing_portraits)

        self.champ_data = {
            int(champ_data["data"][champ_name]["key"]): champ_data["data"][champ_name]
            for champ_name in champ_data["data"]
        }

    def fetch_latest_patch(self):
        url = "https://ddragon.leagueoflegends.com/api/versions.json"
        response_json = requests.get(url).json()
        return response_json[0]

    def fetch_detailed_champ_data(self, champ_key):
        url = f"https://ddragon.leagueoflegends.com/cdn/{self.patch}/data/en_US/champion/{champ_key}.json"
        data = requests.get(url).json()

        champ_id = data["data"][champ_key]["key"]

        with open(f"champ_data/{champ_id}.json", "w", encoding="utf-8") as fp:
            json.dump(data, fp)

    def fetch_champ_data(self):
        url = f"http://ddragon.leagueoflegends.com/cdn/{self.patch}/data/en_US/champion.json"
        data = requests.get(url).json()

        if not os.path.exists("champ_data"):
            os.mkdir("champ_data")

        with open("latest_data.json", "w", encoding="utf-8") as fp:
            json.dump(data, fp)

        for champ_key in data["data"]:
            print(f"Fetching JSON data for '{champ_key}'")
            self.fetch_detailed_champ_data(champ_key)
            sleep(0.5)

        return data

    def get_missing_portraits(self, champion_data):
        missing_files = []
        for champ_name in champion_data["data"]:
            champ_id = int(champion_data["data"][champ_name]["key"])
            with open(f"champ_data/{champ_id}.json", "r", encoding="utf-8") as fp:
                champ_data = json.load(fp)["data"][champ_name]

            for skin in champ_data["skins"]:
                num = skin["num"]
                if skin["name"].startswith("Prestige") or f"{champ_name.lower()}_{num}" in IGNORED_SKINS:
                    continue

                filename = f"portraits/{champ_id}_{num}.{IMG_FILE_TYPE}"
                if not os.path.exists(filename):
                    missing_files.append((filename, num, champ_name))

        return missing_files

    def fetch_all_portraits(self, skin_list):
        base_url = "https://raw.communitydragon.org/latest/game/assets/characters"

        if not os.path.exists("portraits"):
            os.mkdir("portraits")
        
        for filename, skin_num, champ_name in skin_list:
            name_id = champ_name.lower()

            if f"{name_id}_{skin_num}" in SPECIAL_SKIN_CASES:
                skin_id_attempts = SPECIAL_SKIN_CASES[f"{name_id}_{skin_num}"]
            elif name_id in SPECIAL_SKIN_CASES:
                skin_id_attempts = [skin.replace("[num]", str(skin_num)) for skin in SPECIAL_SKIN_CASES[name_id]]
            else:
                if skin_num == 0:
                    skin_id_attempts = [f"{name_id}_circle", f"{name_id}_circle_{skin_num}"]
                else:
                    skin_id_attempts = [f"{name_id}_circle_{skin_num}", f"{name_id}_circle_{skin_num}.skins_{name_id}_skin{skin_num}"]

                skin_id_attempts.extend([f"{name_id}_circle_{skin_num}.{name_id}"])

            for skin_id in skin_id_attempts:
                url = f"{base_url}/{name_id}/hud/{skin_id}.{IMG_FILE_TYPE}"
                print(f"Downloading champion portrait for '{champ_name}': {skin_id}.{IMG_FILE_TYPE}")

                response = requests.get(url)
                if response.status_code != 200:
                    print("Failed! Status:", response.status_code)
                else:
                    with open(filename, "wb") as fp_out:
                        for chunk in response.iter_content(chunk_size=128):
                            fp_out.write(chunk)

                sleep(0.5)

if __name__ == "__main__":
    data_handler = DataHandler()

    with open("latest_data.json", "r", encoding="utf-8") as fp:
        champ_data = json.load(fp)

    # missing_files = data_handler.get_missing_portraits(champ_data)
    # for filename, num, champ_name in missing_files:
    #     print(champ_name, num)

    # print("Total:", len(missing_files))

    missing_portraits = data_handler.get_missing_portraits(champ_data)
    data_handler.fetch_all_portraits(missing_portraits)
