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

## 好友房

一人選「建立好友房」，看到六位房號後傳給朋友。另一人選「加入好友房」並輸入房號。房號保留五分鐘，房主取消或斷線後失效，配對成功後不能再用同一房號加入該場。好友房和 Quick Match 使用各自的等待隊列。兩台 iPhone 都需要安裝支援好友房的同一版 IPA。連線選單內建數字鍵盤。

### 給 iOS 端的 TCP 協定

所有欄位都是 ASCII，沒有附加換行或 NUL。既有的 78 位元組版本識別為 `OpenLF2 TCP 1\n` 加 64 個十六進位字元。TCP 是串流，接收端應依長度累積資料，再依目前狀態解讀回覆。

| 功能 | 客戶端送出 | 中繼回覆 |
| --- | --- | --- |
| Quick Match | 原本的 78 位元組版本識別 | 配對後回覆 `H` 或 `G` |
| 建立好友房 | `C` + 版本識別，共 79 位元組 | `R` + 六位房號，之後配對回 `H`。等候逾時回 `T` 並關閉連線 |
| 加入好友房 | `J` + 版本識別 + 六位房號，共 85 位元組 | 成功回 `G`。房號不存在、已失效或已被使用回 `N`。版本不符回 `X`。失敗後關閉連線，可建立新連線重試 |

雙方讀取 `H` 或 `G` 後，使用現有 OpenLF2 握手和對戰封包。房主保留原連線等候配對，取消時直接關閉連線。加入端輸錯有效格式的房號，可以回到輸入畫面重試。中繼只將同一個版本識別的玩家配在一起。房號用於指定配對，知道房號的人可以嘗試加入。

可在本機執行中繼測試。

```sh
python3 -m unittest discover -s online -p 'test_*.py' -v
```
