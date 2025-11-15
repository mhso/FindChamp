import json
import cv2

from main import get_portraits_data, get_best_match, extract_portrait, process_video
from data_handler import DataHandler

if __name__ == "__main__":
    data_handler = DataHandler()

    with open("latest_data.json", "r", encoding="utf-8") as fp:
        champ_data = json.load(fp)

    print("Loading champion portraits...")
    portraits = get_portraits_data(data_handler)

    print("Trying to match input image...")
    test_video = "/mnt/e/Highlights/League of Legends/League of Legends 2022.04.18 - 22.11.27.09.DVR.mp4" #cv2.imread("test_image.png", cv2.IMREAD_COLOR)

    data = process_video(test_video, portraits)

    print(data)

    #portrait = extract_portrait(test_image)

    # cv2.imshow("Window", portrait)
    # cv2.waitKey(0)

    # best_match = get_best_match(portrait, portraits)
    # max_similarity_data, max_similarity = best_match

    # print(f"Champion with max similarity ({max_similarity}): {max_similarity_data["champ_data"]['name']}")
