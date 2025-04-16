# -*- coding: utf-8 -*-
"""
Created on Wed Apr 16 12:48:40 2025

@author: hhasada
"""

import pandas as pd

# 入力ファイル（再アップロードが必要）
input_csv_path = "agoop_test.csv"
output_csv_path = "../input/points.csv"

# CSV読み込みと変換
df = pd.read_csv(input_csv_path)

df["datetime"] = pd.to_datetime(df[["year", "month", "day", "hour", "minute"]])
df["id"] = df["uuid"]

df.to_csv(output_csv_path, index=False)