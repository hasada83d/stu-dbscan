# stu-dbscan：GPSデータからの滞在・移動・トリップ抽出ツール

## 概要

stu-dbscan (Spatio-Temporal Unified DBSCAN)は，時系列のポイント型GPSデータから「滞在」と「移動」を判定し，トリップを抽出する Python スクリプトです．  
密度ベースクラスタリング手法であるDBSCANを用いて，時空間を統合的に扱った簡潔なパラメータのもと，柔軟にトリップ判定を行います．


## 入力データ形式

CSVファイルに以下の4列が必要です：

| カラム名   | 説明                     |
|------------|--------------------------|
| `id`       | 個体識別子（ユーザーIDなど） |
| `datetime` | 日時（例: `2023-09-01 08:00`） |
| `latitude` | 緯度（10進数）            |
| `longitude`| 経度（10進数）            |

※ `datetime` カラムは `YYYY-MM-DD HH:MM[:SS]` の形式にしてください．

なお、よく使われるポイント型データからこの形式へ変換するコードも用意しています．


## 使用方法

1. `config.ini` ファイルを作成（下記参照）
2. ターミナルなどでスクリプトを実行

```bash
python stu-dbscan.py
```
※ CSVデータの時刻や緯度経度に欠損がある場合，処理対象外となります．

## 設定ファイル例（config.ini）

```ini
[PATH]
input_path = input\points.csv
output_path = output

[PARAMETERS]
threas_walk = 40            ; 徒歩速度[m/分]
threas_stay = 5             ; 滞在とみなす最小時間[分]
thread_warp = 60            ; 空白時間のしきい値[分]

[CRS]
input_crs = EPSG:4326       ; 入力データのcrs
projected_crs = EPSG:6690   ; 入力データを平面投影するcrs（平面直角座標系）
```


## 出力ファイル

すべて `output_path` に以下のCSV形式で出力されます：

| ファイル名               | 内容                     |
|--------------------------|--------------------------|
| `<入力ファイル名>_interpolated.csv` | 補間も含む全観測点と滞在判定 |
| `<入力ファイル名>_observation.csv` | 補間点を除いた滞在・移動データ |
| `<入力ファイル名>_trip.csv`         | 出発地 (`o`) と目的地 (`d`) のみ抽出されたトリップデータ |


## アルゴリズム概要

1. 1分間隔で線形補間し，観測点を補完します．
2. **x, y, z** の3次元空間で DBSCAN を用いて，「滞在」クラスタと「移動」ノイズを分類します．  
   - `z` は時間軸を徒歩速度でスケーリングした値
3. 補間点を除外し，滞在の間を「トリップ」として抽出します．
4. 一定時間（例：60分）空白のあるトリップは削除または分割します．

※ CSVデータの時刻や緯度経度に欠損がある場合，処理対象外となります．

## 引用・利用について / Citation

本モジュール（**STU-DBSCAN: Spatio-Temporal Unified DBSCAN**）を研究やプロジェクト等でご利用いただく際は、以下のURLを明記してください：

> https://github.com/hasada83d/stu-dbscan

論文・報告書等に引用される場合は、以下のように記載してください：

> Hasada, H. (2025). STU-DBSCAN: Spatio-Temporal Unified DBSCAN.

## 参考文献

- Ester, M., H. Kriegel, J. Sander, and Xiaowei Xu. 1996. “A Density-Based Algorithm for Discovering Clusters in Large Spatial Databases with Noise.” Knowledge Discovery and Data Mining, August, 226–31.
- Birant, Derya, and Alp Kut. 2007. “ST-DBSCAN: An Algorithm for Clustering Spatial–Temporal Data.” Data & Knowledge Engineering 60 (1): 208–21. 
- 説明スライド: `stu-dbscan.pdf`（本リポジトリ参照）
