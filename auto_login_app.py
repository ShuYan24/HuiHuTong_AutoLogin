# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, messagebox
import requests
import time
import json
import threading
import os
import sys
from pathlib import Path
import winreg

# ================= 配置文件相关 =================
# 使用 Path.home() 获取用户主目录，然后构建到 AppData\Roaming 的路径
APP_NAME = "HuiHuTong_Autologin"  # 定义一个应用名，用于创建子文件夹
CONFIG_DIR = Path.home() / "AppData" / "Roaming" / APP_NAME
CONFIG_DIR.mkdir(parents=True, exist_ok=True)  # 确保目录存在，如果不存在则创建
CONFIG_FILE = CONFIG_DIR / "config.json" # 配置文件将位于 C:\Users\用户名\AppData\Roaming\HuiHuTong_Autologin\config.json

DEFAULT_CONFIG = {
    "operator": "telecom",
    "username": "",
    "password": "",
    "auto_start_enabled": False,
    "check_interval": 10,
    "login_retry_delay": 5
}

OPERATOR_MAP = {
    "中国电信": "telecom",
    "中国移动": "cmcc",
}

def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        for key in DEFAULT_CONFIG:
            if key not in config:
                config[key] = DEFAULT_CONFIG[key]
        return config
    except FileNotFoundError:
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=4)

# ================= 网络与登录核心逻辑 =================
class NetworkMonitor:
    def __init__(self, config):
        self.config = config
        self.running = False
        self.LOGIN_URL = "http://10.10.16.12/api/portal/v1/login"
        self.CHECK_URL = "http://www.baidu.com"
        self.HEADERS = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "http://10.10.16.12",
            "Referer": "http://10.10.16.12/portal/",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0"
        }

    def check_network(self):
        try:
            response = requests.get(self.CHECK_URL, timeout=3)
            return response.status_code == 200 and "baidu.com" in response.text
        except requests.RequestException:
            return False

    def do_login(self):
        domain = self.config["operator"]
        username = self.config["username"]
        password = self.config["password"]
        
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 检测到断网，正在尝试自动登录 ({domain})...")
        try:
            payload = json.dumps({
                "domain": domain,
                "username": username,
                "password": password
            })
            response = requests.post(self.LOGIN_URL, headers=self.HEADERS, data=payload, timeout=5)
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 服务器响应状态码: {response.status_code}")
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 服务器返回内容: {response.text}")
            return response.status_code == 200
        except requests.RequestException as e:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 登录请求发送失败: {e}")
            return False

    def start_monitoring(self, status_callback=None):
        self.running = True
        while self.running:
            if not self.check_network():
                login_success = self.do_login()
                delay = self.config["login_retry_delay"] if not login_success else 2

                time.sleep(delay)
                if self.check_network():
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🎉 网络已成功恢复！")
                    if status_callback:
                        status_callback("网络已连接")
                else:
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ 登录后网络仍未恢复，将在 {self.config['check_interval']} 秒后重试。")
                    if status_callback:
                        status_callback("登录失败，正在重试...")

            time.sleep(self.config['check_interval'])

    def stop_monitoring(self):
        self.running = False

# ================= 开机自启功能 =================
def set_auto_start(enable: bool):
    key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
    app_name = "TelecomAutoLoginApp"
    executable_path = str(Path(sys.argv[0]).resolve())

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            if enable:
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, executable_path)
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
        return True
    except Exception as e:
        print(f"设置开机自启失败: {e}")
        return False

# ================= GUI 应用程序 =================
class AutoLoginApp:
    def __init__(self, root):
        self.root = root
        self.root.title("慧湖通-宽带防掉线工具 v1.0")
        self.root.minsize(500, 400)
        
        self.monitor = None
        self.monitor_thread = None
        self.status_var = tk.StringVar(value="状态: 未运行")
        self.auto_start_var = tk.BooleanVar(value=False)

        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="20 20 20 10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        frame_config = ttk.LabelFrame(main_frame, text="账户配置", padding="15 10")
        frame_config.pack(fill=tk.X, padx=0, pady=(0, 15))
        
        ttk.Label(frame_config, text="运营商:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10), pady=5)
        self.operator_combo = ttk.Combobox(frame_config, values=list(OPERATOR_MAP.keys()), state="readonly", width=22)
        self.operator_combo.grid(row=0, column=1, sticky=tk.EW, padx=0, pady=5)

        ttk.Label(frame_config, text="用户名:").grid(row=1, column=0, sticky=tk.W, padx=(0, 10), pady=5)
        self.entry_username = ttk.Entry(frame_config, width=25)
        self.entry_username.grid(row=1, column=1, sticky=tk.EW, padx=0, pady=5)

        ttk.Label(frame_config, text="密码:").grid(row=2, column=0, sticky=tk.W, padx=(0, 10), pady=5)
        self.entry_password = ttk.Entry(frame_config, width=25, show="*")
        self.entry_password.grid(row=2, column=1, sticky=tk.EW, padx=0, pady=5)

        frame_config.columnconfigure(1, weight=1)

        self.show_password_var = tk.BooleanVar()
        self.toggle_password_button = ttk.Checkbutton(
            frame_config, text="显示密码", variable=self.show_password_var, command=self.toggle_password_visibility
        )
        self.toggle_password_button.grid(row=3, column=1, sticky=tk.E, padx=0, pady=5)

        frame_buttons = ttk.Frame(main_frame)
        frame_buttons.pack(fill=tk.X, padx=0, pady=10)

        self.btn_save = ttk.Button(frame_buttons, text="💾 保存配置", command=self.save_settings, width=12)
        self.btn_save.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_test_login = ttk.Button(frame_buttons, text="🔍 测试登录", command=self.test_login, width=12)
        self.btn_test_login.pack(side=tk.LEFT, padx=5)

        self.btn_toggle_monitor = ttk.Button(frame_buttons, text="🚀 启动监控", command=self.toggle_monitoring, width=12)
        self.btn_toggle_monitor.pack(side=tk.RIGHT, padx=(10, 0))

        chk_frame = ttk.Frame(main_frame)
        chk_frame.pack(fill=tk.X, pady=10)
        self.chk_auto_start = ttk.Checkbutton(
            chk_frame, text="开机自动启动此程序", variable=self.auto_start_var, command=self.on_auto_start_change
        )
        self.chk_auto_start.pack(anchor=tk.W)

        status_frame = ttk.Frame(self.root, padding="20 10 20 20")
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        status_label = ttk.Label(status_frame, text="状态:")
        status_label.pack(side=tk.LEFT)
        
        status_info_label = ttk.Label(status_frame, textvariable=self.status_var, foreground='blue')
        status_info_label.pack(side=tk.LEFT, padx=(5, 0))

    def toggle_password_visibility(self):
        if self.show_password_var.get():
            self.entry_password.config(show="")
        else:
            self.entry_password.config(show="*")

    def load_settings(self):
        config = load_config()
        operator_display_name = next((name for name, domain in OPERATOR_MAP.items() if domain == config.get("operator", "")), list(OPERATOR_MAP.keys())[0])
        self.operator_combo.set(operator_display_name)
        
        self.entry_username.delete(0, tk.END)
        self.entry_username.insert(0, config.get("username", ""))
        self.entry_password.delete(0, tk.END)
        self.entry_password.insert(0, config.get("password", ""))
        self.auto_start_var.set(config.get("auto_start_enabled", False))

    def save_settings(self):
        selected_operator_display = self.operator_combo.get()
        selected_domain = OPERATOR_MAP.get(selected_operator_display, "telecom")

        config = load_config()
        config.update({
            "operator": selected_domain,
            "username": self.entry_username.get().strip(),
            "password": self.entry_password.get().strip(),
        })
        save_config(config)
        messagebox.showinfo("保存成功", "配置已保存！")

    def on_auto_start_change(self):
        """当“开机自动启动”复选框状态改变时触发"""
        enabled = self.auto_start_var.get()
        success = set_auto_start(enabled)
        if success:
            # 成功设置系统自启后，立即更新配置文件中的状态
            config = load_config()
            config["auto_start_enabled"] = enabled
            save_config(config)
            print(f"系统自启设置已{'启用' if enabled else '禁用'}，配置文件已同步。")
        else:
            # 如果系统设置失败，UI复选框状态回滚，提示用户
            self.auto_start_var.set(not enabled)
            messagebox.showerror("错误", "设置开机自启失败，请检查权限。")

    def test_login(self):
        def run_test():
            selected_operator_display = self.operator_combo.get()
            selected_domain = OPERATOR_MAP.get(selected_operator_display, "telecom")
            
            temp_config = {
                "operator": selected_domain,
                "username": self.entry_username.get().strip(),
                "password": self.entry_password.get().strip(),
            }
            monitor = NetworkMonitor(temp_config)
            
            self.status_var.set("正在测试登录...")
            try:
                success = monitor.do_login()
                if success:
                    self.status_var.set("测试登录成功！")
                else:
                    self.status_var.set("测试登录失败！")
            except Exception as e:
                self.status_var.set(f"测试出错 - {str(e)}")
        
        threading.Thread(target=run_test, daemon=True).start()

    def toggle_monitoring(self):
        if not self.monitor or not self.monitor.running:
            if not all([self.operator_combo.get(), self.entry_username.get().strip(), self.entry_password.get().strip()]):
                messagebox.showwarning("警告", "请先填写完整的账户信息！")
                return
            
            self.save_settings()
            config = load_config()
            self.monitor = NetworkMonitor(config)
            
            def update_status(msg):
                self.status_var.set(msg)
            
            self.monitor_thread = threading.Thread(target=self.monitor.start_monitoring, args=(update_status,), daemon=True)
            self.monitor_thread.start()
            self.btn_toggle_monitor.config(text="⏹️ 停止监控")
            self.status_var.set("监控已启动")
        else:
            self.monitor.stop_monitoring()
            self.btn_toggle_monitor.config(text="🚀 启动监控")
            self.status_var.set("监控已停止")

    def on_closing(self):
        """当点击窗口右上角X按钮时触发"""
        # 不直接销毁窗口，而是将其图标化（最小化到任务栏）
        self.root.iconify()
        # 可选：弹出一个提示，告知用户程序仍在后台运行
        # messagebox.showinfo("提示", "程序已最小化到后台运行。", parent=self.root)


def main():
    root = tk.Tk()
    app = AutoLoginApp(root)
    
    # 绑定窗口关闭事件，使其最小化而非退出
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    if getattr(sys, 'frozen', False):
        if len(sys.argv) > 1 and sys.argv[1] == '--startup':
            config = load_config()
            if config.get("auto_start_enabled", False):
                app.toggle_monitoring()

    root.mainloop()

if __name__ == "__main__":
    main()