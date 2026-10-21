#!/usr/bin/env python3
"""
生成中国 IPv4 CIDR 清单（尽量全）。

数据源（四源合并取并集，再折叠）：
  1. APNIC 官方分配表  delegated-apnic-latest  (最权威，按国家注册)
  2. gaoyifan/china-operator-ip ip-lists/china.txt  (按运营商汇总)
  3. Loyalsoldier/geoip release/text/cn.txt
  4. ym/chnroutes2 chnroutes.txt  (BGP 实际路由聚合，含新分配但注册表未更新的段)

输出：china_ip_list.txt，每行一个 CIDR，升序。
只依赖标准库。
"""
import ipaddress
import sys
import urllib.request
from pathlib import Path

OUT = Path("china_ip_list.txt")

UA = {"User-Agent": "Mozilla/5.0 (china-ip-list generator)"}

# 依次尝试直连和镜像
SOURCES = {
    "apnic": [
        "https://ftp.apnic.net/apnic/stats/apnic/delegated-apnic-latest",
    ],
    "gaoyifan": [
        "https://raw.githubusercontent.com/gaoyifan/china-operator-ip/ip-lists/china.txt",
        "https://ghproxy.net/https://raw.githubusercontent.com/gaoyifan/china-operator-ip/ip-lists/china.txt",
    ],
    "loyalsoldier": [
        "https://raw.githubusercontent.com/Loyalsoldier/geoip/release/text/cn.txt",
        "https://ghproxy.net/https://raw.githubusercontent.com/Loyalsoldier/geoip/release/text/cn.txt",
    ],
    "chnroutes2": [
        "https://raw.githubusercontent.com/ym/chnroutes2/master/chnroutes.txt",
        "https://ghproxy.net/https://raw.githubusercontent.com/ym/chnroutes2/master/chnroutes.txt",
    ],
}


def fetch(urls, name):
    last = None
    for u in urls:
        try:
            req = urllib.request.Request(u, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read().decode("utf-8", errors="ignore")
            if data.strip():
                print(f"  {name}: OK  <- {u}  ({len(data)} bytes)")
                return data
            last = f"空响应: {u}"
        except Exception as e:
            last = f"{u} -> {e}"
            print(f"  {name}: 失败 {last}")
    raise RuntimeError(f"{name} 全部地址失败: {last}")


def parse_apnic(text):
    """APNIC delegated 格式：registry|cc|type|start|value|date|status"""
    nets = []
    for line in text.splitlines():
        f = line.strip().split("|")
        if len(f) < 5 or f[1] != "CN" or f[2] != "ipv4":
            continue
        ip, cnt = f[3], int(f[4])
        plen = 32 - (cnt.bit_length() - 1)
        try:
            nets.append(ipaddress.ip_network(f"{ip}/{plen}", strict=False))
        except ValueError:
            pass
    return nets


def parse_cidr(text):
    """普通 CIDR 文本，跳过注释和空行"""
    nets = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            n = ipaddress.ip_network(line, strict=False)
        except ValueError:
            continue
        if n.version == 4:
            nets.append(n)
    return nets


def main():
    print("拉取数据源...")
    apnic = parse_apnic(fetch(SOURCES["apnic"], "apnic"))
    gaoyifan = parse_cidr(fetch(SOURCES["gaoyifan"], "gaoyifan"))
    loyalsoldier = parse_cidr(fetch(SOURCES["loyalsoldier"], "loyalsoldier"))
    chnroutes = parse_cidr(fetch(SOURCES["chnroutes2"], "chnroutes2"))

    print(f"\n原始条数: apnic={len(apnic)} gaoyifan={len(gaoyifan)} "
          f"loyalsoldier={len(loyalsoldier)} chnroutes2={len(chnroutes)}")

    allv4 = apnic + gaoyifan + loyalsoldier + chnroutes

    # 去重 + 排序 + 折叠相邻段
    uniq = sorted(set(allv4), key=lambda n: (int(n.network_address), n.prefixlen))
    collapsed = list(ipaddress.collapse_addresses(uniq))

    total = sum(n.num_addresses for n in collapsed)

    # 健全性检查：条数和覆盖范围都要合理，否则拒绝输出
    if not (3000 <= len(collapsed) <= 20000):
        sys.exit(f"❌ 条数异常 ({len(collapsed)})，拒绝写入")
    if not (2.0e8 <= total <= 6.0e8):
        sys.exit(f"❌ 覆盖 IP 数异常 ({total})，拒绝写入")

    # 每个都必须合法
    bad = [str(n) for n in collapsed if not isinstance(n, ipaddress.IPv4Network)]
    if bad:
        sys.exit(f"❌ 有非 IPv4 段: {bad[:5]}")

    OUT.write_text("\n".join(str(n) for n in collapsed) + "\n", encoding="utf-8")

    print(f"\n合并去重 {len(uniq)} -> 折叠后 {len(collapsed)} 条")
    print(f"覆盖 {total:,} 个 IP ({total / 2**32 * 100:.2f}% 的 IPv4 空间)")
    print(f"已写入 {OUT} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
