# 終極 LF2 iOS 野團測試

兩台 iPhone 安裝同一版「終極 LF2 連線測試」。在連線選單進入 **Quick Match**，輸入相同的中繼伺服器 IPv4 位址，可附上連接埠，然後按 **Match**。伺服器依相同版本的連線識別配對。配對後進入原有的連線遊戲選單。

測試伺服器可用 Python 3.10 以上啟動。

```sh
python3 online/relay.py
```

同網路測試時請輸入伺服器的區域網路位址。跨網路測試需要將 TCP 12346 對外開放，或使用指向此連接埠的 TCP 代理，再把公開 IPv4 和連接埠填入 App。中繼使用和遊戲相同的 TCP 資料流，目前適合受控測試。

Docker 部署可用 `online` 作為 build context。

```sh
docker build -t lf2-relay online
docker run --rm -p 12346:12346/tcp lf2-relay
```
