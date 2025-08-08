import requests
from bs4 import BeautifulSoup
import pandas as pd
from requests.auth import HTTPBasicAuth
import numpy as np


def create_package(package_name):
    try:
        session = requests.Session()
        # 1. 登录（示例：Cookie 认证，也可改用 HTTPBasicAuth）
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0...",
                "Cookie": "openSUSE_session=1c0126a0fe72de8f0c723576c04f4793; _session_id=86e1eaf57fbec2c1dc9327329561a8eb",  # 从浏览器复制有效 Cookie
            }
        )

        # 2. 访问创建页面，提取 token
        create_url = "https://build.opensuse.org/package/new/home:lalala123:experiment2"
        resp = session.get(create_url)
        soup = BeautifulSoup(resp.text, "html.parser")
        token = soup.find("input", {"name": "authenticity_token"})["value"]

        # 3. 提交创建请求
        payload = {
            "authenticity_token": token,
            "package[name]": package_name,
            "package[title]": "",  # 补充空字段
            "package[description]": "",  # 补充空字段
            "commit": "Create",
        }
        create_url = (
            "https://build.opensuse.org/package/create/home:lalala123:experiment2"
        )
        resp = session.post(create_url, data=payload, allow_redirects=True)

        if (
            "package/show/home:lalala123:experiment2/{}".format(package_name)
            in resp.url
        ):
            return True
        else:
            return False
    except Exception as e:
        print("创建失败！", package_name, e)
        return False


class RebuildPackage:
    def __init__(self, user_name, password, obs_url, project_name, target_project_name):
        self.user_name = user_name
        self.password = password
        self.auth = HTTPBasicAuth(user_name, password)
        self.obs_url = obs_url
        self.project_name = project_name
        self.target_project_name = target_project_name

    def copy_fetch(self, package_name, rev, code):
        if code == "failed":
            target_package_name = f"{code}_{package_name}"
        else:
            target_package_name = package_name

        url = f"{self.obs_url}/source"

        # 设置请求参数
        params = {
            "cmd": "branch",
            "project": self.project_name,
            "package": package_name,
            "target_project": self.target_project_name,
            "target_package": target_package_name,
            "rev": rev,
        }

        # 发送POST请求
        response = requests.post(
            url,
            params=params,
            auth=self.auth,
            headers={"Accept": "application/xml; charset=utf-8"},
            timeout=3600,  # 添加3600秒超时限制，避免请求无限等待
        )

        # 处理响应
        if response.status_code in (200, 201):
            print(
                f"包 '{package_name}' 已成功分支到 '{self.target_project_name}/{target_package_name}'"
            )
        else:
            print(f"分支失败！状态码: {response.status_code}")
            print(f"错误信息: {response.text}")


if __name__ == "__main__":
    # package_name = pd.read_csv("pkgs.csv")["pkg"].tolist()
    # res_pkgs = pd.DataFrame(columns=["package_name", "status"])
    # for pkg in package_name:
    #     failed_pkg_name = f"failed_{pkg}"
    #     res_pkgs = pd.concat([res_pkgs, pd.DataFrame([{"package_name": pkg, "status": create_package(failed_pkg_name)}])], ignore_index=True)
    # res_pkgs.to_csv("pkgs_status.csv", index=False)

    api_url = "https://api.opensuse.org"
    project = "openSUSE:Factory:RISCV"
    target_project = "home:lalala123:RISCV"
    obs_username = "lalala123"
    obs_password = "zhaochenyu921"

    rebuild_package = RebuildPackage(obs_username, obs_password, api_url, project, target_project)

    after_create_pkg = pd.read_csv("after_parallel_build_status_full_openSUSE:Factory:RISCV_standard_riscv64.csv")
    valid_pkgs = set(after_create_pkg["package"].tolist())

    for i in range(0, len(after_create_pkg), 2):
        # 取当前组的两行数据（若最后一组不足2行，取现有行）
        group = after_create_pkg.iloc[i : i + 2]
        pkg_name = group.iloc[0]["package"]

        # 跳过不在有效包列表中的包
        if pkg_name not in valid_pkgs:
            continue

        prev, next_ = group.iloc[0], group.iloc[1] if len(group) > 1 else None
        build_times = [prev["build_time"]]
        if next_ is not None:
            build_times.append(next_["build_time"])
        max_build_time = max(build_times)
        # 过滤构建时间过长的包
        if int(max_build_time) > 3600:
            continue

        rebuild_package.copy_fetch(pkg_name, prev["rev"], prev["code"])
        if next_ is not None:
            rebuild_package.copy_fetch(pkg_name, next_["rev"], next_["code"])
