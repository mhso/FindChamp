from argparse import ArgumentParser
from main import DataHandler

if __name__ == "__main__":
    data_handler = DataHandler()

    parser = ArgumentParser()
    parser.add_argument("champion", choices=[entry["name"].lower() for entry in  data_handler.champ_data.values()])
    args = parser.parse_args()

    for champ_id in data_handler.champ_data:
        if data_handler.champ_data[champ_id]["name"].lower() == args.champion:
            print(champ_id)
