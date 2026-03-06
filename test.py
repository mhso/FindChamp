from argparse import ArgumentParser
import json

import cv2

from main import get_portraits_data, process_video, get_best_match, extract_portrait
from data_handler import DataHandler

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("file")
    args = parser.parse_args()

    data_handler = DataHandler()

    with open("latest_data.json", "r", encoding="utf-8") as fp:
        champ_data = json.load(fp)

    print("Loading champion portraits...")
    portraits = get_portraits_data(data_handler)

    if args.file.endswith("mp4"):
        file_type = "video"
    else:
        file_type = "image"

    print(f"Trying to match input {file_type}...")

    if file_type == "video":
        best_match = process_video(args.file, portraits)
    else:
        test_data = cv2.imread(args.file, cv2.IMREAD_COLOR)
        portrait = extract_portrait(args.file, test_data)
        best_match = get_best_match(portrait, portraits)

    if best_match is None:
        print("No match!")
        exit(0)

    max_similarity_data, max_similarity = best_match

    print(f"Champion with max similarity ({max_similarity}): {max_similarity_data["champ_data"]['name']}")
