# ECNU Network Keeper

一个用于华东师大校园网登录、断网和自动保活的工具。

它支持：

- 手动登录 / 断网
- `daemon` 常驻保活
- Linux `systemd` 服务化
- Docker 运行
- 本地加密保存账号信息
- 断网 / 恢复时间记录

默认账号后缀已经设为 `@stu.ecnu.edu.cn`，普通学生账号一般不需要额外配置 domain。

## Quick Start

最推荐的首次使用方式是直接在宿主机上运行。

### 1. 保存账号密码

```bash
python3 -m ecnu_network_keeper --update --store-password
```

输入提示里：

- `Student ID [...]` 直接回车可以使用默认值
- `Domain suffix [...]` 默认就是 `@stu.ecnu.edu.cn`，普通学生账号直接回车即可
- `Password:` 输入密码即可

### 2. 登录

```bash
python3 -m ecnu_network_keeper --login
```

### 3. 断网

```bash
python3 -m ecnu_network_keeper --logout
```

### 4. 常驻保活

```bash
python3 -m ecnu_network_keeper --login --daemon --verbose
```

## 目录结构

- `ecnu_network_keeper/`: 主程序源码
- `tests/`: 单元测试
- `data/`: 运行时状态和配置目录，例如 `keeper-state.json`、`config.ini`
- `logs/`: 运行日志目录，例如 `keeper-events.log`
- `artifacts/`: 导出的镜像包等大文件产物目录
- `deploy/docker/`: Docker 相关文件
- `deploy/systemd/`: `systemd` 相关文件

## 命令总览

下面这些是最常用的命令。

### 本地命令

```bash
python3 -m ecnu_network_keeper --update --store-password
```
作用：交互式输入学号、domain、密码，并把它们加密保存到本地配置文件。

```bash
python3 -m ecnu_network_keeper --login
```
作用：使用当前可用凭据登录校园网。

```bash
python3 -m ecnu_network_keeper --login --verbose
```
作用：登录并输出更详细的连通性检测和门户响应信息，适合排障。

```bash
python3 -m ecnu_network_keeper --logout
```
作用：断开校园网连接。会优先使用已保存账号，不要求你重新输入密码。

```bash
python3 -m ecnu_network_keeper --logout --verbose
```
作用：断网并输出详细日志。

```bash
python3 -m ecnu_network_keeper --login --daemon --verbose
```
作用：以常驻模式运行，周期性检测网络状态，掉线后自动重连。

```bash
python3 -m ecnu_network_keeper --login --daemon --interval 60 --verbose
```
作用：常驻模式，每 60 秒检查一次网络。

### 参数说明

- `--login`: 执行登录
- `--logout`: 执行断网 / 登出
- `--update`: 更新并保存凭据
- `--daemon`: 常驻运行
- `--interval N`: `daemon` 模式下每隔多少秒检查一次
- `--verbose`: 输出详细日志
- `--store-password`: 把凭据加密保存到本地配置文件
- `--domain`: 手动覆盖账号后缀，例如 `@cmcc`
- `--config`: 指定配置文件路径
- `--username` / `--password`: 直接通过命令行传入账号密码

## 方案一：直接运行

这是最直接、最推荐的方式。

### 保存账号密码

```bash
python3 -m ecnu_network_keeper --update --store-password
```

### 登录

```bash
python3 -m ecnu_network_keeper --login
```

### 查看详细输出

```bash
python3 -m ecnu_network_keeper --login --verbose
```

### 断网 / 登出

```bash
python3 -m ecnu_network_keeper --logout
```

查看详细输出：

```bash
python3 -m ecnu_network_keeper --logout --verbose
```

说明：

- `--logout` 会优先使用本地已保存的账号信息
- 如果本地已经保存了当前账号，即使没有保存密码，也不会因为断网再次要求输入密码

### 重新登录

如果当前已经在线，直接执行 `--login` 会提示网络已连接，不会重复登录。

需要手动重登时，建议：

```bash
python3 -m ecnu_network_keeper --logout
python3 -m ecnu_network_keeper --login
```

## 方案二：常驻保活模式

如果你想让程序持续检查网络状态，并在掉线后自动重新登录，可以直接运行：

```bash
python3 -m ecnu_network_keeper --login --daemon --verbose
```

说明：

- 默认每 `120` 秒检查一次
- 可以通过 `--interval` 调整间隔
- 运行日志会打印到当前终端
- 断网记录会写到 `logs/keeper-events.log`
- 当前状态会写到 `data/keeper-state.json`

例如每 60 秒检查一次：

```bash
python3 -m ecnu_network_keeper --login --daemon --interval 60 --verbose
```

停止方式：

- 前台运行时：按 `Ctrl+C`
- 后台运行时：结束对应进程

## 方案三：Linux systemd 服务

如果你不想手动开着终端，更推荐在 Linux 上配成 `systemd` 服务。

### 1. 先写入凭据

```bash
python3 -m ecnu_network_keeper --update --store-password
```

### 2. 安装服务

```bash
sudo bash deploy/systemd/install_systemd_service.sh
```

安装脚本会自动：

- 生成 `/etc/systemd/system/ecnu-network-keeper.service`
- 设定项目根目录为 `WorkingDirectory`
- 默认以 `python3 -m ecnu_network_keeper --login --daemon --verbose` 方式运行
- 自动执行 `systemctl enable`

### 3. 启动服务

```bash
sudo systemctl start ecnu-network-keeper
```

### 4. 停止服务

```bash
sudo systemctl stop ecnu-network-keeper
```

### 5. 重启服务

```bash
sudo systemctl restart ecnu-network-keeper
```

### 6. 查看服务状态

```bash
sudo systemctl status ecnu-network-keeper
```

### 7. 查看服务日志

```bash
sudo journalctl -u ecnu-network-keeper -f
```

### 8. 开机自启 / 取消开机自启

```bash
sudo systemctl enable ecnu-network-keeper
sudo systemctl disable ecnu-network-keeper
```

### 9. 卸载服务

```bash
sudo systemctl stop ecnu-network-keeper
sudo systemctl disable ecnu-network-keeper
sudo rm -f /etc/systemd/system/ecnu-network-keeper.service
sudo systemctl daemon-reload
```

### 10. 使用环境文件而不是本地配置

如果你不想把密码保存进本地配置文件，可以参考：

- `deploy/systemd/.env.example`

自己新建：

- `deploy/systemd/.env`

安装脚本默认会把它作为 `EnvironmentFile` 读取。

如果你要自定义安装参数，也可以这样：

```bash
sudo bash deploy/systemd/install_systemd_service.sh --user YOUR_USER --python /usr/bin/python3 --interval 60
```

## 方案四：Docker

Docker 适合“已经能提前准备镜像”的场景。

如果目标机器一开始没网，第一次 `docker build` / `docker pull` 往往会失败，因为基础镜像 `python:3.12-slim` 拉不下来。

默认提供的 Docker 镜像包是：

- `E:\PythonProjects\ecnu_network_keeper\artifacts\ecnu-network-keeper.tar`

也就是项目根目录下的：

- `./artifacts/ecnu-network-keeper.tar`

优先推荐的使用顺序是：

1. 先导入默认镜像
2. 再用 compose 启动容器

### 4.1 导入默认镜像

如果你已经拿到了默认镜像包，先执行：

```bash
docker load -i artifacts/ecnu-network-keeper.tar
```

如果镜像包放在别的位置，就把路径换成对应位置即可。

导入完成后，`docker compose` 会直接使用：

- `ecnu-network-keeper:latest`

### 4.2 启动前直接提供凭据

先从示例文件复制：

```bash
cp deploy/docker/.env.example deploy/docker/.env
```

然后编辑 `deploy/docker/.env`，填入：

```env
ECNU_NET_USERNAME=你的学号
ECNU_NET_PASSWORD=你的密码
ECNU_NET_DOMAIN=@stu.ecnu.edu.cn
ECNU_NET_SECRET_KEY=
```

普通学生账号如果用默认后缀，`ECNU_NET_DOMAIN` 也可以不改。

这一种方式里，`deploy/docker/.env` 中的账号和密码属于明文保存。

也就是说：

- `ECNU_NET_USERNAME=...`
- `ECNU_NET_PASSWORD=...`

会直接以普通文本形式出现在 `.env` 文件里。

这种方式的优点是启动简单，但它不属于“加密存储凭据”。

然后启动：

```bash
docker compose -f deploy/docker/docker-compose.yml --env-file deploy/docker/.env up -d
```

这条命令默认不会在本机重新构建镜像，更适合离线服务器场景。

如果你明确想在本机重新构建镜像，请先手动执行：

```bash
docker build -f deploy/docker/Dockerfile -t ecnu-network-keeper:latest .
```

### 4.3 先启动容器，后输入凭据

先启动容器：

```bash
docker compose -f deploy/docker/docker-compose.yml up -d
```

然后把账号密码写进容器挂载卷：

```bash
docker exec -it ecnu-network-keeper python -m ecnu_network_keeper --update --store-password --config /data/config.ini
```

写入成功后，容器里的 keeper 下一轮检测就会自动尝试登录。

这一种方式属于“交互输入后加密保存”：

- 你在当前终端输入的密码不会回显
- 凭据最终会加密写入 `/data/config.ini`
- 不需要把密码明文写进 `deploy/docker/.env`

如果你更在意密码落盘安全，推荐优先使用这一种方式。

### 4.4 启动 / 停止 / 重启 Docker keeper

启动：

```bash
docker compose -f deploy/docker/docker-compose.yml --env-file deploy/docker/.env up -d
```

停止：

```bash
docker compose -f deploy/docker/docker-compose.yml stop
```

重启：

```bash
docker compose -f deploy/docker/docker-compose.yml restart
```

删除容器：

```bash
docker compose -f deploy/docker/docker-compose.yml down
```

### 4.5 查看 Docker 日志

看运行日志：

```bash
docker logs -f ecnu-network-keeper
```

看断网/恢复事件日志：

```bash
tail -f ./logs/keeper-events.log
```

### 4.6 Docker 下如何断网

因为容器默认在跑 `--login --daemon`，所以只执行登出还不够，后台 keeper 会再次自动登录。

通常建议：

```bash
docker exec -it ecnu-network-keeper python -m ecnu_network_keeper --logout --config /data/config.ini
docker compose -f deploy/docker/docker-compose.yml stop
```

也就是说：

- `--logout` 负责断网
- `docker compose stop` 负责防止 keeper 再次自动连上

### 4.7 Docker 的限制

使用 Docker 时要特别注意：

- 容器网络环境不一定等于宿主机网络环境
- 在校园网场景下，认证结果可能依赖宿主机实际网络命名空间
- Linux 下如果桥接网络行为不符合预期，可能需要评估 `network_mode: host`

## 离线首次部署

这个项目现在已经是“零第三方运行时依赖”，所以如果目标机器本身有 Python 3，首次部署时最稳的方式通常不是 Docker，而是：

```bash
python3 -m ecnu_network_keeper --login
```

如果你一定要用 Docker，但目标机器没网，建议在另一台有网机器上：

1. 先构建镜像
2. 导出成 `tar`
3. 再拷到目标机器导入

例如：

```bash
docker buildx build --platform linux/amd64 -f deploy/docker/Dockerfile -t ecnu-network-keeper:latest --load .
docker save -o artifacts/ecnu-network-keeper.tar ecnu-network-keeper:latest
```

然后在目标机器：

```bash
docker load -i artifacts/ecnu-network-keeper.tar
```

## 环境变量

常用环境变量如下：

- `ECNU_NET_USERNAME`: 学号
- `ECNU_NET_PASSWORD`: 密码
- `ECNU_NET_DOMAIN`: 账号后缀，默认 `@stu.ecnu.edu.cn`
- `ECNU_NET_SECRET_KEY`: 外部提供的主密钥
- `ECNU_NET_CONFIG`: 配置文件路径
- `ECNU_NET_KEY_PATH`: 密钥文件路径
- `ECNU_KEEPER_INTERVAL`: keeper 检查间隔
- `ECNU_KEEPER_EVENT_LOG`: 事件日志路径
- `ECNU_KEEPER_STATE_PATH`: 状态文件路径

## 日志与状态文件

默认情况下，当前仓库建议统一放到：

- `logs/keeper-events.log`
- `data/keeper-state.json`

含义分别是：

- `keeper-events.log`: 记录断网、恢复、首次启动状态切换
- `keeper-state.json`: 记录上一次观测到的联网状态

## 安全说明

- `--store-password` 会加密保存账号、密码和 domain
- 当前实现只依赖 Python 标准库，目标是“避免明文落盘 + 支持离线首装”
- 如果你需要更强的密钥隔离，优先使用 `ECNU_NET_SECRET_KEY`
- 如果密钥文件和配置文件放在同一目录，安全收益主要是“避免明文直接泄露”，不是强隔离

可以把“明文使用”和“加密使用”简单理解成下面两类：

- 明文账号密码：把 `ECNU_NET_USERNAME`、`ECNU_NET_PASSWORD` 直接写进 `deploy/docker/.env`，或者直接通过命令行参数传入。这种方式使用方便，但密码本身就是明文。
- 加密存储账号密码：运行 `python3 -m ecnu_network_keeper --update --store-password`，或者在 Docker 容器里运行 `docker exec -it ecnu-network-keeper python -m ecnu_network_keeper --update --store-password --config /data/config.ini`。这种方式是交互输入，然后把凭据加密写入配置文件。

需要特别注意：

- `.env` 里的密码不会因为程序支持加密存储而自动变成加密内容
- 只有 `--update --store-password` 这类“写入配置文件”的路径，才会真正把凭据按加密形式落盘
- 如果你已经把密码写进 `.env`，那么加密存储只能保护后续写入的配置文件，不能消除 `.env` 这一份明文风险

如果你需要生成新的主密钥，可以调用：

```python
from ecnu_network_keeper.config import generate_secret_key
print(generate_secret_key().decode())
```

## 注意事项

1. 首次没网时，不推荐先折腾 Docker。
优先直接用宿主机 Python 登录，把网络打通后再考虑 Docker。

2. Docker 不是一定优于本地 Python。
对“校园网登录 + 掉线重连”这种需求，Linux 下 `systemd + 本地 Python` 往往更直接、更稳。

3. Docker 断网时记得停 keeper。
否则它可能马上又帮你重新登录。

4. 普通学生账号一般不用手填 domain。
默认就是 `@stu.ecnu.edu.cn`。

5. `Student ID [...]` 这类提示里，方括号中的值是默认值，直接回车即可。

6. 断网事件记录的是 keeper 检测到状态变化的时间，不是网络实际断开的精确毫秒时刻。

