# -*- coding: utf-8 -*-
"""
Created on Mon Sep  4 13:44:06 2023
Modified for .ini configuration input with CRS support

@author: hhasada
"""

import os
import math
import pandas as pd
import geopandas as gpd
import numpy as np
from datetime import datetime, timedelta
from sklearn.cluster import DBSCAN

def get_utm_epsg(latitude: float, longitude: float) -> int:
    """
    緯度経度から対応するUTMゾーンのEPSGコードを取得する関数（WGS84基準）
    
    Parameters:
        latitude (float): 緯度（-90〜90）
        longitude (float): 経度（-180〜180）

    Returns:
        int: EPSGコード（例：32654 for UTM zone 54N）
    """
    if not -80.0 <= latitude <= 84.0:
        raise ValueError("UTM座標系は緯度84N〜80Sまでが対象です。")
    
    # UTMゾーンの計算
    zone = int((longitude + 180) / 6) + 1
    
    # 北半球ならEPSG: 326XX, 南半球ならEPSG: 327XX
    if latitude >= 0:
        epsg_code = 32600 + zone
    else:
        epsg_code = 32700 + zone

    return  "EPSG:"+str(epsg_code)


def stu_dbscan(
    points: pd.DataFrame,
    thres_walk: float,
    thres_stay: float,
    thres_warp: float,
    interp_freq: str = '1min',
    input_crs: str = "EPSG:4326",
    projected_crs: str = "EPSG:xxxx",
):
    
    # 投影する平面直角座標
    if projected_crs == "EPSG:xxxx":
        projected_crs  = get_utm_epsg(points["latitude"].median(),points["longitude"].median())

    # 重複・欠損除去・順番整理
    points = points.drop_duplicates(['id', 'datetime']).dropna(subset=['latitude', 'longitude'])
    points = points.sort_values(['id', 'datetime'])
    points["time"] = pd.to_datetime(points["datetime"])
    
    # GeoDataFrame化とCRS投影
    points["geometry"] = gpd.points_from_xy(points["longitude"], points["latitude"], crs=input_crs).to_crs(projected_crs)
    points = gpd.GeoDataFrame(points)
    points["x"] = points["geometry"].x
    points["y"] = points["geometry"].y
    
    ###################
    # stay or move
    ###################
    # ① interpolate列とstay列を新たに作り、すべて0とする。
    points = points[["id", "x", "y", "time",'latitude', 'longitude', "geometry"]]
    points['interpolate'] = 0
    #points['stay'] = 0
    
    # ② interp_freqごとに、x,yの値を線形補間する。補間したデータのinterpolate列を1とする。
    interp_list = []
    for uid, grp in points.groupby('id'):
        t0, t1 = grp['time'].min(), grp['time'].max()
        all_times = pd.date_range(t0, t1, freq=interp_freq)
        tmp = grp.set_index('time').reindex(all_times)
        # 補間マーク: 元データにない行は interpolate=1
        tmp['interpolate'] = np.where(tmp['id'].isna(), 1, 0)
        tmp['id'] = uid
        tmp['x'] = tmp['x'].interpolate()
        tmp['y'] = tmp['y'].interpolate()
        tmp = tmp.reset_index().rename(columns={'index':'time'})
        interp_list.append(tmp)
    interp_gdf = pd.concat(interp_list, ignore_index=True)

    # ③  1分刻みデータ抽出 (秒=00) 、timeをunix時間（分）へ変換し、threas_walk*√3を掛けたものをz列とする。
    one_min_df = interp_gdf[interp_gdf['time'].dt.second == 0].copy()
    one_min_df['z'] = one_min_df['time'].apply(
        lambda x: x.timestamp() * thres_walk * math.sqrt(3) / 60
    )
    
    # ④ x,y,z列について、dbscanを行う。eps = threas_walk*threas_stay/2、MinPts = threas_stay/2する。corepoint、noisepoint となったデータのstay列を1とする。
    one_min_df['stay'] = 0
    for uid, grp in one_min_df.groupby('id'):
        coords = grp[['x','y','z']].values
        labels = DBSCAN(
            eps=thres_walk*thres_stay/2,
            min_samples=int(thres_stay/2)
        ).fit_predict(coords)
        one_min_df.loc[grp.index,'stay'] = (labels != -1).astype(int)

    # ⑤ 補間データにマージ & 前後埋め
    interp_gdf = interp_gdf.merge(
        one_min_df[['id','time','stay']],
        on=['id','time'], how='left')
    interp_gdf['stay'] = interp_gdf['stay'].fillna(method='ffill').fillna(method='bfill').fillna(0).astype(int)
    interp_gdf['stay_str'] = interp_gdf['stay'].map({1:'stay',0:'move'})
    
    
    # 最終的なデータフレーム
    interp_gdf = gpd.GeoDataFrame(
    interp_gdf,
    geometry=gpd.points_from_xy(interp_gdf.x, interp_gdf.y, crs=projected_crs)
    ).to_crs(input_crs)
    interp_gdf["longitute"] = interp_gdf["geometry"].x
    interp_gdf["latitude"] = interp_gdf["geometry"].y
    
    result_df = points.merge(
        interp_gdf[['id','time','stay','stay_str']],
        on=['id','time'], how='left'
    )
    #"result_df = gpd.GeoDataFrame(result_df, geometry='geometry', crs=input_crs)
    #result_df["longitude"] = result_df["geometry"].x
    #result_df["latitude"] = result_df["geometry"].y
    
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
    
    # "id"ごとに"time"列の前後の差を計算し、thres_warp分以上の間隔があるかつ移動判定の場合に"od"列を"w"に設定
    result_df['time_diff'] = result_df.groupby('id')['time'].diff()
    result_df['time_diff_'] = result_df.groupby('id')['time'].diff(periods=-1)
    result_df.loc[((result_df['time_diff'] >= pd.Timedelta(minutes=thres_warp)) |
                   (result_df['time_diff_'] <= pd.Timedelta(minutes=-thres_warp))) &
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
    trip_df = result_df_od[['id', 'time', 'longitude', 'latitude', 'x', 'y', 'od']].copy().reset_index(drop=True)
    trip_df_shifted = trip_df.shift(-1).reset_index(drop=True) # データフレームを上にずらる
    trip_df = trip_df.merge(trip_df_shifted, right_index=True, left_index=True, suffixes=["_o", "_d"]) # データフレームを横に結合
    trip_df = trip_df[(trip_df["id_o"] == trip_df["id_d"]) & (trip_df["od_o"] == "o") & (trip_df["od_d"] == "d")] # ODのid一致を確認
    trip_df = trip_df.rename(columns={"id_o": "id"}).drop(["id_d", "od_o", "od_d"], axis=1)
    
    trip_df["time_delta"] = trip_df["time_d"] - trip_df["time_o"]
    trip_df["direct_dist(m)"] = ((trip_df["x_o"] - trip_df["x_d"]) ** 2 + (trip_df["y_o"] - trip_df["y_d"]) ** 2) ** 0.5
    trip_df["direct_vel(km/h)"] = trip_df["direct_dist(m)"] * 3.6 / trip_df["time_delta"].dt.total_seconds()
    
    interp_df=interp_gdf[['id', 'time', 'latitude', 'longitude', 'interpolate', 'stay', 'stay_str']].rename(columns={"time":"datetime"})
    result_df=result_df[['id', 'time', 'latitude', 'longitude', 'interpolate', 'stay', 'stay_str', 'odw', 'time_diff']].rename(columns={"time":"datetime"})
    trip_df=trip_df[['id', 'time_o', 'longitude_o', 'latitude_o', 'time_d','longitude_d', 'latitude_d', 'time_delta','direct_dist(m)', 'direct_vel(km/h)']].rename(columns={"time_o":"datetime_o","time_d":"datetime_d"})
    
    return interp_df, result_df, trip_df