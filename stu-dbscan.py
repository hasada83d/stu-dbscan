# -*- coding: utf-8 -*-
"""
Created on Mon Sep  4 13:44:06 2023
Modified for .ini configuration input with CRS support

@author: hhasada
"""

import pandas as pd
import geopandas as gpd
import math
import configparser
import os
from sklearn.cluster import DBSCAN
from datetime import datetime, timedelta
import time

# 時間計測開始
time_sta = time.time()

###################
# Read Parameters from .ini
###################
config = configparser.ConfigParser()
config.read('input/config.ini', encoding='utf-8')

params = config['PARAMETERS']
paths = config['PATH']
crs_config = config['CRS']

# 数値パラメータ
threas_walk = float(params['threas_walk'])
threas_stay = float(params['threas_stay'])
thread_warp = float(params['thread_warp'])

# パス
input_path = paths['input_path']
output_dir = paths['output_path']
base_name = os.path.splitext(os.path.basename(input_path))[0]

# CRS設定
input_crs = crs_config['input_crs']
projected_crs = crs_config['projected_crs']

###################
# Input
###################
points = pd.read_csv(input_path)
print("finished: input")

###################
# stay or move
###################
points = points[~points[["latitude", "longitude"]].isna().any(axis=1)]
points = points.drop_duplicates(subset=["id", "datetime"], keep=False)

points["geometry"] = gpd.points_from_xy(points["longitude"], points["latitude"], crs=input_crs).to_crs(projected_crs)
points = gpd.GeoDataFrame(points)
points["x"] = points["geometry"].x
points["y"] = points["geometry"].y

points["time"] = pd.to_datetime(points["datetime"])

df = points[["id", "x", "y", "time"]]
del points

# ⓪ id、timeでソートする
df = df.sort_values(by=['id', 'time'])
df['interpolate_x'] = 0
df['stay'] = 0

# ① interpolate列とstay列を新たに作り、すべて0とする。
interpolated_df = pd.DataFrame()
for group_id, group_df in df.groupby('id'):
    min_time = group_df['time'].min()
    max_time = group_df['time'].max()
    new_times = pd.date_range(start=min_time, end=max_time, freq='1min')
    interpolated_group_df = group_df.set_index('time').reindex(new_times).interpolate(method='linear')
    interpolated_group_df['interpolate_y'] = 1
    interpolated_group_df['id'] = group_id
    interpolated_df = pd.concat([interpolated_df, interpolated_group_df])

# ② time1分ごとに、x,yの値を線形補間する。補間したデータのinterpolate列を1とする。
interpolated_df = interpolated_df.reset_index().rename(columns={"index": "time"})
df = pd.merge(df[['id', 'time', 'interpolate_x']], interpolated_df.drop('interpolate_x', axis=1), on=['id', 'time'], how='right')
df["interpolate_x"] = df["interpolate_x"].fillna(1)
df["interpolate"] = df["interpolate_x"] * df["interpolate_y"]

# ③ timeをunix時間（分）へ変換し、threas_walk*√3を掛けたものをz列とする。
df['z'] = (df['time'].apply(lambda x: x.timestamp()).astype(int) * threas_walk * math.sqrt(3) / 60)

# ④ x,y,z列について、dbscanを行う。eps = threas_walk*threas_stay/2、MinPts = threas_stay/2する。corepoint、noisepoint となったデータのstay列を1とする。
for group_id, group_df in df.groupby('id'):
    coordinates = group_df[['x', 'y', 'z']].values
    dbscan = DBSCAN(eps=threas_walk * threas_stay / 2, min_samples=int(threas_stay / 2)).fit(coordinates)
    group_df['stay'] = (dbscan.labels_ != -1).astype(int)
    df.loc[group_df.index, 'stay'] = group_df['stay']

# ⑤ interpolate列が0のものだけ抽出する。
filtered_df = df[df['interpolate'] == 0]

# 最終的なデータフレーム
result_df = filtered_df[['id', 'time', 'x', 'y', 'z', 'interpolate', 'stay']]
result_df["geometry"] = gpd.points_from_xy(result_df["x"], result_df["y"], crs=projected_crs).to_crs(input_crs)
result_df = gpd.GeoDataFrame(result_df)
result_df["lon"] = result_df["geometry"].x
result_df["lat"] = result_df["geometry"].y
result_df["stay_str"] = result_df["stay"].apply(lambda x: "stay" if x == 1 else "move")

df["geometry"] = gpd.points_from_xy(df["x"], df["y"], crs=projected_crs).to_crs(input_crs)
df = gpd.GeoDataFrame(df)
df["lon"] = df["geometry"].x
df["lat"] = df["geometry"].y

df.to_csv(os.path.join(output_dir, f"{base_name}_interpolated.csv"), index=False)
print("finished: stay or move")

###################
# warp
###################
# 列"stay"を基に"od"列を設定	
### 0の直前が1となる行における列"od"の値を"o"、0の直後が1となる行における列"od"の値を"d"

result_df["odw"] = ""
prev_index = None
prev_stay = None
prev_id = None
for index, row in result_df.iterrows():
    if row['stay'] == 1 and prev_id == row["id"]:
        if prev_stay == 0:
            result_df.at[index, 'odw'] = 'd'
    elif row['stay'] == 0 and prev_id == row["id"]:
        if prev_stay == 1:
            result_df.at[prev_index, 'odw'] = 'o'
    prev_index = index
    prev_stay = row["stay"]
    prev_id = row["id"]

# "id"ごとに"time"列の前後の差を計算し、thread_warp分以上の間隔があるかつ移動判定の場合に"od"列を"w"に設定
result_df['time_diff'] = result_df.groupby('id')['time'].diff()
result_df['time_diff_'] = result_df.groupby('id')['time'].diff(periods=-1)
result_df.loc[((result_df['time_diff'] >= pd.Timedelta(minutes=thread_warp)) |
               (result_df['time_diff_'] <= pd.Timedelta(minutes=-thread_warp))) &
              (result_df['stay'] == 0), 'odw'] = 'w'


# 列"odw"を基に"od"列を設定	
### wの直前がoとなる行における列"od"の値を"ow"、wの直後がdとなる行における列"od"の値を"dw"
result_df_odw = result_df[result_df["odw"].isin(["o", "d", "w"])]
result_df_odw["od"] = result_df_odw["odw"].copy()

prev_index = None
prev_odw = None
prev_id = None
for index, row in result_df_odw.iterrows():
    if row['odw'] == "d" and prev_id == row["id"]:
        if prev_odw in ["w", "d"]:
            result_df_odw.at[index, 'od'] = 'dw'
    elif row['odw'] == "o" and prev_id == row["id"]:
        if prev_odw == "o":
            result_df_odw.at[prev_index, 'od'] = 'ow'
    elif row['odw'] == "w" and prev_id == row["id"]:
        if prev_odw == "o":
            result_df_odw.at[prev_index, 'od'] = 'ow'
    prev_index = index
    prev_odw = row["odw"]
    prev_id = row["id"]

print("finished: warp")

###################
# trip
###################
result_df_od = result_df_odw[result_df_odw["od"].isin(["o", "d"])]


# 各"id"について、一番最初の"od"列が"d"の場合は"od"列を"dw"に、一番最後の"od"列が"o"の場合は"od"列を"ow"に設定
first_index = result_df_od.groupby('id').head(1).index
last_index = result_df_od.groupby('id').tail(1).index
result_df_od.loc[result_df_od.index.isin(first_index) & (result_df_od["od"] == "d"), 'od'] = 'dw'
result_df_od.loc[result_df_od.index.isin(last_index) & (result_df_od["od"] == "o"), 'od'] = 'ow'
result_df_od = result_df_od[result_df_od["od"].isin(["o", "d"])]

#トリップデータ作成
trip_df = result_df_od[['id', 'time', 'lon', 'lat', 'x', 'y', 'od']].copy().reset_index(drop=True)
trip_df_shifted = trip_df.shift(-1).reset_index(drop=True) # データフレームを上にずらる
trip_df = trip_df.merge(trip_df_shifted, right_index=True, left_index=True, suffixes=["_o", "_d"]) # データフレームを横に結合
trip_df = trip_df[(trip_df["id_o"] == trip_df["id_d"]) & (trip_df["od_o"] == "o") & (trip_df["od_d"] == "d")] # ODのid一致を確認
trip_df = trip_df.rename(columns={"id_o": "id"}).drop(["id_d", "od_o", "od_d"], axis=1)

trip_df["time_delta"] = trip_df["time_d"] - trip_df["time_o"]
trip_df["direct_dist(m)"] = ((trip_df["x_o"] - trip_df["x_d"]) ** 2 + (trip_df["y_o"] - trip_df["y_d"]) ** 2) ** 0.5
trip_df["direct_vel(km/h)"] = trip_df["direct_dist(m)"] * 3.6 / trip_df["time_delta"].dt.total_seconds()

result_df.to_csv(os.path.join(output_dir, f"{base_name}_observation.csv"), index=False)
trip_df.to_csv(os.path.join(output_dir, f"{base_name}_trip.csv"), index=False)

# 時間計測終了
time_end = time.time()
print(f"{time_end - time_sta:.2f} 秒")
