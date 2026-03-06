import json
import os
from time import sleep
from argparse import ArgumentParser

import requests
from bs4 import BeautifulSoup

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
    def __init__(self):
        patch_versions = self.fetch_patch_versions()
        self.latest_patch = patch_versions[0]
        self.major_patches = self.get_major_patches(patch_versions)
        self.new_patches = []
        self.patches_to_remove = []

        if os.path.exists("latest_data.json"):
            with open("latest_data.json", "r", encoding="utf-8") as fp:
                champ_data = json.load(fp)

            if champ_data["version"] != self.latest_patch:
                self.new_patches.append(self.latest_patch)

                # Remove old patch data if this is a minor patch
                if champ_data["version"].split(".")[0] == self.latest_patch.split(".")[0]:
                    self.patches_to_remove.append(champ_data["version"])
        else:
            print("Performing first time setup...")
            self.new_patches = self.major_patches

        champ_data_dicts = []
        for index, patch in enumerate(self.new_patches):
            latest = index == len(self.new_patches) - 1
            patch_name = f"latest patch '{patch}'" if latest else f"patch '{patch}'"
            print(f"Fetching metadata for {patch_name}...")
            champ_data = self.fetch_champ_data(patch, latest)
            champ_data_dicts.append(champ_data)
            sleep(0.25)

            if latest:
                with open("latest_data.json", "w", encoding="utf-8") as fp:
                    json.dump(champ_data, fp)

        for index, (patch, champ_data) in enumerate(zip(self.new_patches, champ_data_dicts)):
            if int(patch.split(".")[0]) < 9:
                continue

            latest = index == len(self.new_patches) - 1
            patch_name = f"latest patch '{patch}'" if latest else f"patch '{patch}'"
            print(f"Fetching portraits for {patch_name}...")
            missing_portraits, old_files = self.get_missing_portraits(patch, self.new_patches[:index], champ_data)
            self.fetch_skin_portraits(patch, missing_portraits, old_files)

        self.champ_data = {
            int(champ_data["data"][champ_name]["key"]): champ_data["data"][champ_name]
            for champ_name in champ_data["data"]
        }

    def get_major_patches(self, versions):
        patches_major = set()
        patches_full = []
        for patch in reversed(versions):
            if not patch.startswith("lolpatch"):
                major = int(patch.strip().split(".")[0])
                if major >= 3 and major not in patches_major:
                    patches_major.add(major)
                    patches_full.append(patch)

        # Latest patch should be entirely up to date
        patches_full[-1] = versions[0]

        return patches_full

    def fetch_patch_versions(self):
        url = "https://ddragon.leagueoflegends.com/api/versions.json"
        response_json = requests.get(url).json()
        return response_json

    def fetch_detailed_champ_data(self, patch, champ_id):
        url = f"https://ddragon.leagueoflegends.com/cdn/{patch}/data/en_US/champion/{champ_id}.json"

        response = requests.get(url)
        if response.status_code == 404:
            print(f"Data for '{champ_id}' on patch '{patch}' could not be found")
            return
        elif response.status_code != 200:
            print(f"Error ({response.status_code}): {response.text}")
            return

        data = response.json()

        champ_key = data["data"][champ_id]["key"]

        with open(f"champ_data/{patch}/{champ_key}.json", "w", encoding="utf-8") as fp:
            json.dump(data, fp)

    def fetch_champ_data(self, patch: str, latest: bool = False, fetch_details: bool = True):
        url = f"http://ddragon.leagueoflegends.com/cdn/{patch}/data/en_US/champion.json"
        data = requests.get(url).json()

        if not os.path.exists(f"champ_data/{patch}"):
            os.makedirs(f"champ_data/{patch}")

        if fetch_details:
            for champ_id in data["data"]:
                champ_key = data["data"][champ_id]["key"]
                if not latest and os.path.exists(f"champ_data/{patch}/{champ_key}.json"):
                    continue

                print(f"Fetching JSON data for '{champ_id}'")
                self.fetch_detailed_champ_data(patch, champ_id)
                sleep(0.5)

        return data

    def get_missing_portraits(self, patch, prev_patches, champion_data):
        old_files = {}
        missing_files = []

        for champ_name in champion_data["data"]:
            champ_id = int(champion_data["data"][champ_name]["key"])

            champ_metadata_file = f"champ_data/{patch}/{champ_id}.json"
            if not os.path.exists(champ_metadata_file):
                continue

            with open(champ_metadata_file, "r", encoding="utf-8") as fp:
                champ_data = json.load(fp)["data"][champ_name]

            for skin in champ_data["skins"]:
                num = skin.get("num", 0)

                filename = f"portraits/{patch}/{champ_id}_{num}"
                if not os.path.exists(f"{filename}.{IMG_FILE_TYPE}"):
                    missing_files.append((filename, num, champ_name))
                else:
                    for prev_patch in prev_patches:
                        old_filename = f"portraits/{prev_patch}/{champ_id}_{num}.{IMG_FILE_TYPE}"
                        if os.path.exists(old_filename):
                            old_files[filename] = old_filename

        return missing_files, old_files

    def fetch_portrait_for_champion(self, portrait_url: str, output_filename: str):
        response = requests.get(portrait_url, timeout=10)

        if response.status_code != 200:
            print(f"Failed! [{portrait_url}], Status: {response.status_code}")
            return False
        else:
            with open(output_filename, "wb") as fp:
                for chunk in response.iter_content(chunk_size=512):
                    fp.write(chunk)

            return True

    def fetch_skins_from_data_dragon(self, patch, missing_files, old_files):
        pass

    def fetch_character_portrait_urls(self, url: str):
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
        except Exception as exc:
            print(f"Exception when getting character portrait from '{url}'!")
            print(exc)
            if response and response.status_code >= 500:
                print("Abandoning because community dragon has issues...")
                exit(0)

        soup = BeautifulSoup(response.text, features="html.parser")

        images = []
        tables = soup.find_all("table")
        for table in tables:
            body = table.find("tbody")

            for row in body.find_all("tr"):
                td_2 = row.find("td", class_="link")
                img = td_2.find("a")
                if img is None:
                    continue

                href = img.attrs["href"]
                if "circle" not in href:
                    continue

                images.append(f"{url}/{href}")

        return images

    def match_skin_ids_with_portraits(self, skin_num, portrait_urls):
        skins_matching = []
        for url in portrait_urls:
            img_filename = url.split("/")[-1]
            if str(skin_num) in img_filename:
                skins_matching.append(url)

            elif skin_num == 0 and not any(str(num) in img_filename for num in range(1, 10)):
                skins_matching.append(url)

        return skins_matching

    def fetch_skins_from_community_dragon(self, patch, missing_files):
        url_patch = ".".join(patch.split(".")[:-1])
        base_url = f"https://raw.communitydragon.org/{url_patch}/game/assets/characters"

        if not os.path.exists(f"portraits/{patch}"):
            os.makedirs(f"portraits/{patch}")

        unique_champ_names = set(x[2].lower() for x in missing_files)
        image_urls = {}
        for champ_name in unique_champ_names:
            name_id = champ_name.lower()
            champ_url = f"{base_url}/{name_id}/hud"
            portrait_urls = self.fetch_character_portrait_urls(champ_url)
            image_urls[name_id] = portrait_urls
            print(f"Found {len(portrait_urls)} portraits for '{name_id}'")
            sleep(2)

        for filename, skin_num, champ_name in missing_files:
            name_id = champ_name.lower()
            skin_portrait_urls = self.match_skin_ids_with_portraits(skin_num, image_urls[name_id])
            if skin_portrait_urls == []:
                print(f"Can't match skin {champ_name}_{skin_num} with portraits:")
                print(image_urls[name_id])
                continue

            for index, url in enumerate(skin_portrait_urls):
                if index > 0:
                    filename = f"{filename}_{index}.{IMG_FILE_TYPE}"

                print(f"Downloading champion portrait for '{champ_name}': {os.path.basename(filename)}")
                self.fetch_portrait_for_champion(url, filename)
                sleep(1.5)

    def fetch_skin_portraits(self, patch, missing_files, old_files):
        patch_split = patch.split(".")
        if int(patch_split[0]) > 7:
            self.fetch_skins_from_community_dragon(patch, missing_files)
        else:
            self.fetch_skins_from_data_dragon(patch, missing_files, old_files)

if __name__ == "__main__":
    data_handler = DataHandler()

    parser = ArgumentParser()
    parser.add_argument("patch")
    parser.add_argument("champion", choices=[entry["name"].lower() for entry in  data_handler.champ_data.values()])
    parser.add_argument("skin_id", type=int)
    args = parser.parse_args()

    if len(args.patch.split(".")) != 3:
        print("Invalid patch!")
        exit(0)

    name_id = args.champion

    url_patch = ".".join(args.patch.split(".")[:-1])
    base_url = f"https://raw.communitydragon.org/{url_patch}/game/assets/characters/{name_id}/hud"

    champ_data = next(filter(lambda x: x["name"].lower() == name_id, data_handler.champ_data.values()))

    if args.skin_id is None:
        with open(f"champ_data/{args.patch}/{champ_data["key"]}.json", "r", encoding="utf-8") as fp:
            detailed_champ_data = json.load(fp)

        skins_to_download = detailed_champ_data["data"][champ_data["id"]]["skins"]
    else:
        skins_to_download = [{"num": args.skin_id}]

    for skin_data in skins_to_download:
        skin_num = skin_data["num"]

        if skin_num == 0:
            skin_id_attempts = [f"{name_id}_circle", f"{name_id}_circle_{skin_num}"]
        else:
            skin_id_attempts = [f"{name_id}_circle_{skin_num}", f"{name_id}_circle_{skin_num}.skins_{name_id}_skin{skin_num}"]

        skin_id_attempts.extend([f"{name_id}_circle_{skin_num}.{name_id}"])
        output_filename = f"portraits/{args.patch}/{champ_data['key']}_{skin_num}.{IMG_FILE_TYPE}"

        for skin_id in skin_id_attempts:
            if data_handler.fetch_portrait_for_champion(base_url, skin_id):
                break
