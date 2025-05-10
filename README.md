# stu-dbscan：GPSデータからの滞在・移動・トリップ抽出ツール

## 概要

stu-dbscan (Spatio-Temporal Unified DBSCAN)は，時系列のGPS/GNSS観測点データから「滞在」と「移動」を判定し，トリップを抽出する Python 関数です．  
密度ベースクラスタリング手法であるDBSCANを用いて，時空間を統合的に扱った簡潔なパラメータのもと，柔軟にトリップ判定を行います．

## パラメータ

| パラメータ       | 説明                                                 | 例          |
|------------------|------------------------------------------------------|-------------|
| points           | 観測点データ                                        | 詳細は下記  |
| input_crs        | 入力データの CRS                                     | EPSG:4326   |
| projected_crs    | 投影用の平面 CRS                                     | EPSG:6690   |
| thres_walk       | 徒歩速度スケーリング係数（m/分）                     | 40          |
| thres_stay       | 滞在判定最小時間（分）                               | 5           |
| thres_warp       | 空白時間ギャップ閾値（分）                           | 60          |
| interp_freq      | 線形補間間隔（秒または分単位で指定）                  | 1S/30S/1min |

### 観測点データの形式

以下の4列が必要です：

| カラム名   | 説明                     |
|------------|--------------------------|
| `id`       | 個体識別子（ユーザーIDなど） |
| `datetime` | 日時（例: `2023-09-01 08:00`） |
| `latitude` | 緯度（10進数）            |
| `longitude`| 経度（10進数）            |

※ `datetime` カラムは `YYYY-MM-DD HH:MM[:SS]` の形式にしてください．

なお、よく使われるポイント型データからこの形式へ変換するコードも用意しています．

## 戻り値

| 変数名      | 説明                                      |
|-------------|-------------------------------------------|
| interp_df   | DataFrame; 補間されたものを含む観測点データ（interpolate/stay/stay_str フラグを含む）      |
| result_df   | DataFrame; 元の観測点データ（stay/stay_str フラグを含む）                |
| trip_df     | DataFrame; 抽出されたトリップ区間（出発 o、到着 d）                      |


## アルゴリズム概要

1. `interp_freq`の間隔で線形補間し，観測点を補間
2. 1分間隔で抽出した観測点データについて，**x, y, z** の3次元空間で DBSCAN を用いて「move」クラスタと「stay」ノイズへ分類
   - `z` は時間軸を徒歩速度でスケーリングした値
3. 前後両方の抽出データが 「move」 の場合のみ，元の観測点を 「move」と判定
4. 「stay」の間をトリップとして抽出
5. `thres_warp`の時間空白のあるトリップは削除または分割

※ CSVデータの時刻や緯度経度に欠損がある場合，処理対象外となります．

## 引用・利用について

本モジュール**stu-dbscan (Spatio-Temporal Unified DBSCAN)**を研究やプロジェクト等でご利用いただく際は、以下のURLを明記してください：

> https://github.com/hasada83d/stu-dbscan

論文・報告書等に引用される場合は、例えば以下のように記載してください：

> Hasada, Hiroyuki. 2025. Python Package: stu-dbscan. https://github.com/hasada83d/stu-dbscan.

## 参考文献

- Ester, M., H. Kriegel, J. Sander, and Xiaowei Xu. 1996. “A Density-Based Algorithm for Discovering Clusters in Large Spatial Databases with Noise.” Knowledge Discovery and Data Mining, August, 226–31.
- 説明スライド: `stu-dbscan.pdf`（本リポジトリ参照）
