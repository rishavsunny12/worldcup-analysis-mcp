from understatapi import UnderstatClient
import pandas as pd

understat = UnderstatClient()

leagues = ["EPL", "La_Liga", "Bundesliga", "Serie_A", "Ligue_1", "RFPL"]

for league in leagues:
    player_data = understat.league(league=league).get_player_data(season="2025")
    df = pd.DataFrame(player_data)
    df = df.sort_values(by=["xG"], ascending=False)
    df.to_csv(f"understat_{league}_2025_26_player_stats.csv", index=False)
