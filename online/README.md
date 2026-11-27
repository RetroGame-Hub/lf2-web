# 終極 LF2 iOS 野團測試

兩台 iPhone 安裝同一版「終極 LF2 連線測試」。在連線選單按 **Quick Match**，App 會連到 Railway 中繼 `viaduct.proxy.rlwy.net:59934`。伺服器依相同版本的連線識別配對，成功後會進入原有的連線遊戲選單。

原有 IP 直連可從 **Waiting for Opponent** 和 **Connect to Opponent** 進入。

本機可用 Python 3.10 以上啟動中繼。發布版 App 的 Quick Match 仍會使用預設的 Railway 入口。

```sh
python3 online/relay.py
```

Docker 部署可用 `online` 作為 build context。

```sh
docker build -t lf2-relay online
docker run --rm -p 12346:12346/tcp lf2-relay
```
