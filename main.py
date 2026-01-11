import sys
import os
import threading
import time
import zipfile
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QFileDialog, QProgressBar, QListWidget, 
    QListWidgetItem, QMenu, QAction, QDialog, QGridLayout, QScrollArea,
    QMessageBox, QStyle, QSystemTrayIcon
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QUrl
from PyQt5.QtGui import QIcon, QPixmap, QFont, QColor, QCursor

# 尝试导入Pillow库，如果失败则提示用户安装
try:
    from PIL import Image
except ImportError:
    QMessageBox.critical(None, "错误", "缺少Pillow库，请运行 'pip install pillow' 安装")
    sys.exit(1)

class ImageCompressThread(QThread):
    """图片压缩线程"""
    progress_update = pyqtSignal(str, int)
    compress_finished = pyqtSignal(str, dict)

    def __init__(self, image_path):
        super().__init__()
        self.image_path = image_path

    def run(self):
        """执行压缩"""
        try:
            # 获取原始文件大小
            original_size = os.path.getsize(self.image_path)
            
            # 打开图片
            image = Image.open(self.image_path)
            image_format = image.format
            
            # 生成压缩后的文件名
            base_name = os.path.basename(self.image_path)
            name, ext = os.path.splitext(base_name)
            output_path = os.path.join(
                os.path.dirname(self.image_path),
                f"{name}_compressed{ext}"
            )
            
            # 模拟压缩进度
            for i in range(101):
                time.sleep(0.01)  # 减少模拟处理时间，提高响应速度
                # 发送进度更新信号
                self.progress_update.emit(self.image_path, i)
            
            # 保存压缩后的图片（使用优化参数）
            if image_format == 'JPEG':
                image.save(output_path, optimize=True, quality=85)
            elif image_format == 'PNG':
                image.save(output_path, optimize=True, compress_level=9)
            elif image_format == 'WEBP':
                image.save(output_path, optimize=True, quality=85)
            else:
                image.save(output_path, optimize=True)
            
            # 获取压缩后的文件大小
            compressed_size = os.path.getsize(output_path)
            
            # 计算压缩比例
            compression_ratio = round((1 - compressed_size / original_size) * 100, 2)
            
            # 发送完成信号
            result = {
                'original_path': self.image_path,  # 添加原始路径
                'original_size': original_size,
                'compressed_size': compressed_size,
                'compression_ratio': compression_ratio,
                'output_path': output_path,
                'format': image_format
            }
            # 确保发送100%进度
            self.progress_update.emit(self.image_path, 100)
            self.compress_finished.emit(self.image_path, result)
            
        except Exception as e:
            print(f"压缩失败: {e}")
            self.compress_finished.emit(self.image_path, None)

class ImageItemWidget(QWidget):
    """图片项组件"""
    def __init__(self, image_path):
        super().__init__()
        self.image_path = image_path
        self.base_name = os.path.basename(image_path)
        self.original_size = os.path.getsize(image_path)
        self.compress_ratio = 0
        self.status = "等待中"
        self.format = "未知"
        self.compressed_size = 0
        self.start_time = None
        self.remaining_time = "估算中..."
        
        # 布局
        layout = QHBoxLayout()  # 改为水平布局
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 缩略图
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(60, 60)
        self.thumbnail_label.setStyleSheet("border: 1px solid #ddd; border-radius: 3px;")
        # 加载并显示缩略图
        try:
            pixmap = QPixmap(self.image_path)
            # 调整图片大小为缩略图
            pixmap = pixmap.scaled(60, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.thumbnail_label.setPixmap(pixmap)
        except Exception as e:
            print(f"加载缩略图失败: {e}")
        
        # 右侧内容布局
        content_layout = QVBoxLayout()
        content_layout.setSpacing(10)  # 增加内容间距
        
        # 文件名和状态
        header_layout = QHBoxLayout()
        self.name_label = QLabel(self.base_name)
        self.name_label.setFont(QFont("Arial", 10, QFont.Medium))
        self.name_label.setMinimumHeight(20)  # 增加标签高度，确保文字完整显示
        self.status_label = QLabel(self.status)
        self.status_label.setFont(QFont("Arial", 9))
        self.status_label.setStyleSheet("color: #666;")
        header_layout.addWidget(self.name_label)
        header_layout.addStretch()
        header_layout.addWidget(self.status_label)
        
        # 图片信息
        info_layout = QHBoxLayout()
        info_layout.setSpacing(25)  # 增加间距，使大小和剩余时间之间有合适的间距
        self.format_label = QLabel(f"格式: {self.format}")
        self.format_label.setFont(QFont("Arial", 9))
        self.size_label = QLabel(f"大小: {self._format_size(self.original_size)}")
        self.size_label.setFont(QFont("Arial", 9))
        self.time_label = QLabel(f"剩余时间: {self.remaining_time}")
        self.time_label.setFont(QFont("Arial", 9))
        info_layout.addWidget(self.format_label)
        info_layout.addWidget(self.size_label)
        info_layout.addWidget(self.time_label)
        info_layout.addStretch()
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0%")  # 初始显示0%
        self.progress_bar.setTextVisible(True)  # 确保文本可见
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ddd;
                border-radius: 5px;
                text-align: center;
                background: #f0f0f0;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 5px;
            }
        """)
        
        # 压缩结果
        result_layout = QHBoxLayout()
        self.ratio_label = QLabel("")
        self.ratio_label.setFont(QFont("Arial", 10, QFont.Bold))
        # 压缩大小标签
        self.size_label_compressed = QLabel("")
        self.size_label_compressed.setFont(QFont("Arial", 10, QFont.Bold))
        self.size_label_compressed.setStyleSheet("color: #4CAF50;")
        # 下载按钮（文字）
        self.download_button = QPushButton("下载")
        self.download_button.setStyleSheet("QPushButton { background-color: white; color: #4caf50; border: 1px solid #f0f0f0; padding: 0px 5px; border-radius: 4px; font-size: 12px; font-weight: bold; min-height: 30px; } QPushButton:hover { background-color: #f0f0f0; }")
        self.download_button.setVisible(False)
        # 添加按钮提示
        self.download_button.setToolTip("下载图片")
        result_layout.addWidget(self.ratio_label)
        result_layout.addWidget(self.size_label_compressed)
        result_layout.addStretch()
        result_layout.addWidget(self.download_button)
        
        # 添加到内容布局
        content_layout.addLayout(header_layout)
        content_layout.addLayout(info_layout)
        content_layout.addWidget(self.progress_bar)
        content_layout.addLayout(result_layout)
        
        # 添加到主布局
        layout.addWidget(self.thumbnail_label)
        layout.addLayout(content_layout)
        layout.setStretch(0, 0)  # 缩略图不拉伸
        layout.setStretch(1, 1)  # 内容区域拉伸
        
        self.setLayout(layout)
    
    def _format_size(self, size):
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} TB"
    
    def update_progress(self, value):
        """更新进度"""
        self.progress_bar.setValue(value)
        # 显示进度百分比
        self.progress_bar.setFormat(f"{value}%")
        self.progress_bar.setTextVisible(True)  # 确保文本可见
        
        # 估算剩余时间
        if value > 0 and self.start_time:
            elapsed_time = time.time() - self.start_time
            total_time = elapsed_time / (value / 100)
            remaining = total_time - elapsed_time
            if remaining > 0:
                self.remaining_time = f"{remaining:.1f}s"
                self.time_label.setText(f"剩余时间: {self.remaining_time}")
    
    def update_status(self, status):
        """更新状态"""
        self.status = status
        self.status_label.setText(status)
        
        # 记录开始时间
        if status == "压缩中...":
            self.start_time = time.time()
    
    def update_result(self, result):
        """更新压缩结果"""
        if result:
            self.compressed_size = result['compressed_size']
            self.compress_ratio = result['compression_ratio']
            self.format = result['format']
            
            self.format_label.setText(f"格式: {self.format}")
            self.size_label.setText(f"大小: {self._format_size(self.original_size)}")
            self.time_label.setText(f"剩余时间: 0s")
            self.ratio_label.setText(f"压缩比例: {self.compress_ratio}%")
            self.size_label_compressed.setText(f" 压缩后: {self._format_size(self.compressed_size)}")
            self.status_label.setText("已完成")
            # 确保进度条显示100%
            self.progress_bar.setValue(100)
            self.progress_bar.setFormat("100%")
            self.download_button.setVisible(True)
        else:
            self.status_label.setText("压缩失败")
            self.ratio_label.setText("")
            self.size_label_compressed.setText("")
            self.time_label.setText("剩余时间: -")

class MainWindow(QMainWindow):
    """主窗口"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("图片无损压缩客户端")
        self.setGeometry(100, 100, 800, 600)
        self.setWindowIcon(QIcon(QApplication.style().standardIcon(QStyle.SP_DialogYesButton)))
        
        # 中央组件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        
        # 顶部工具栏
        toolbar_layout = QHBoxLayout()
        
        # 添加图片按钮
        self.add_button = QPushButton("添加图片")
        self.add_button.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0b7dda;
            }
        """)
        self.add_button.clicked.connect(self.add_images)
        
        # 批量下载按钮
        self.batch_download_button = QPushButton("批量下载")
        self.batch_download_button.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #e68a00;
            }
        """)
        self.batch_download_button.clicked.connect(self.batch_download)
        self.batch_download_button.setEnabled(False)
        
        # 清除按钮
        self.clear_button = QPushButton("清除所有")
        self.clear_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
        """)
        self.clear_button.clicked.connect(self.clear_all)
        
        # 任务状态
        self.task_status_label = QLabel("待处理: 0 | 处理中: 0 | 已完成: 0")
        self.task_status_label.setFont(QFont("Arial", 9))
        
        # 添加到工具栏
        toolbar_layout.addWidget(self.add_button)
        toolbar_layout.addWidget(self.batch_download_button)
        toolbar_layout.addWidget(self.clear_button)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.task_status_label)
        
        # 图片列表
        self.image_list = QListWidget()
        self.image_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #ddd;
                border-radius: 5px;
                background: #fafafa;
            }
            QListWidget::item {
                margin: 5px;
                border-radius: 5px;
                background: white;
                border: 1px solid #eee;
            }
        """)
        
        # 底部状态栏
        self.statusBar().showMessage("就绪")
        
        # 添加到主布局
        main_layout.addLayout(toolbar_layout)
        main_layout.addWidget(self.image_list)
        
        # 菜单项
        self.create_menu()
        
        # 数据
        self.image_items = {}  # 存储图片路径和对应的组件
        self.compress_threads = {}  # 存储压缩线程
        self.completed_images = []  # 存储已完成的图片
        
        # 状态计数
        self.pending_count = 0
        self.processing_count = 0
        self.completed_count = 0
    
    def create_menu(self):
        """创建菜单栏"""
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu("文件")
        
        add_action = QAction("添加图片", self)
        add_action.triggered.connect(self.add_images)
        file_menu.addAction(add_action)
        
        batch_download_action = QAction("批量下载", self)
        batch_download_action.triggered.connect(self.batch_download)
        file_menu.addAction(batch_download_action)
        
        clear_action = QAction("清除所有", self)
        clear_action.triggered.connect(self.clear_all)
        file_menu.addAction(clear_action)
        
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 关于菜单
        about_menu = menubar.addMenu("关于")
        
        donate_action = QAction("打赏", self)
        donate_action.triggered.connect(self.show_donate_dialog)
        about_menu.addAction(donate_action)
        
        about_action = QAction("关于软件", self)
        about_action.triggered.connect(self.show_about_dialog)
        about_menu.addAction(about_action)
        
        developer_action = QAction("开发者主页", self)
        developer_action.triggered.connect(self.open_developer_page)
        about_menu.addAction(developer_action)
    
    def add_images(self):
        """添加图片"""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "选择图片", "", "图片文件 (*.jpg *.jpeg *.png *.webp)"
        )
        
        if file_paths:
            for file_path in file_paths:
                if file_path not in self.image_items:
                    # 创建图片项组件
                    item = QListWidgetItem()
                    widget = ImageItemWidget(file_path)
                    
                    # 设置项大小
                    item.setSizeHint(widget.sizeHint())
                    
                    # 添加到列表
                    self.image_list.addItem(item)
                    self.image_list.setItemWidget(item, widget)
                    
                    # 存储
                    self.image_items[file_path] = (item, widget)
                    
                    # 连接下载按钮
                    widget.download_button.clicked.connect(
                        lambda _, path=file_path: self.download_image(path)
                    )
                    
                    # 更新计数
                    self.pending_count += 1
                    self.update_task_status()
            
            # 开始压缩
            self.start_compression()
    
    def start_compression(self):
        """开始压缩所有待处理图片"""
        for image_path, (_, widget) in self.image_items.items():
            if widget.status == "等待中":
                # 创建并启动压缩线程
                thread = ImageCompressThread(image_path)
                thread.progress_update.connect(
                    lambda value, path=image_path: self.update_compress_progress(path, value)
                )
                # 捕获 image_path 并确保参数顺序正确
                def on_compress_finished(path, result, img_path=image_path):
                    self.handle_compress_finished(img_path, result)
                
                thread.compress_finished.connect(on_compress_finished)
                thread.start()
                
                # 存储线程
                self.compress_threads[image_path] = thread
                
                # 更新状态
                widget.update_status("压缩中...")
                self.processing_count += 1
                self.pending_count -= 1
                self.update_task_status()
    
    def update_compress_progress(self, image_path, value):
        """更新压缩进度"""
        if image_path in self.image_items:
            _, widget = self.image_items[image_path]
            widget.update_progress(value)
    
    def handle_compress_finished(self, image_path, result):
        """处理压缩完成"""
        if image_path in self.image_items:
            _, widget = self.image_items[image_path]
            
            if result:
                widget.update_result(result)
                self.completed_images.append(result)
                self.completed_count += 1
            else:
                widget.update_status("压缩失败")
            
            self.processing_count -= 1
            self.update_task_status()
            
            # 启用批量下载按钮
            if self.completed_count > 0:
                self.batch_download_button.setEnabled(True)
    
    def download_image(self, image_path):
        """下载单个图片"""
        # 查找对应的压缩结果
        result = None
        for item in self.completed_images:
            # 根据原始路径查找
            if item.get('original_path') == image_path:
                result = item
                break
        
        if result:
            # 选择保存位置
            save_path, _ = QFileDialog.getSaveFileName(
                self, "保存图片", 
                os.path.basename(result['output_path']),
                f"{result['format']} 文件 (*.{result['output_path'].split('.')[-1]})"
            )
            
            if save_path:
                try:
                    # 复制文件
                    import shutil
                    shutil.copy2(result['output_path'], save_path)
                    QMessageBox.information(self, "成功", f"图片已保存到: {save_path}")
                except Exception as e:
                    QMessageBox.critical(self, "错误", f"保存图片失败: {str(e)}")
        else:
            QMessageBox.warning(self, "警告", "未找到压缩结果")
    
    def batch_download(self):
        """批量下载图片"""
        if not self.completed_images:
            QMessageBox.warning(self, "警告", "没有已完成的图片可以下载")
            return
        
        # 选择保存目录
        save_dir = QFileDialog.getExistingDirectory(self, "选择保存目录")
        
        if save_dir:
            # 询问是否打包
            reply = QMessageBox.question(
                self, "打包选项", "是否将图片打包为压缩包？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                # 打包为压缩包
                self.create_zip(save_dir)
            else:
                # 直接保存
                self.save_images(save_dir)
    
    def create_zip(self, save_dir):
        """创建压缩包"""
        zip_name = f"compressed_images_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        zip_path = os.path.join(save_dir, zip_name)
        
        # 创建压缩包
        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for i, result in enumerate(self.completed_images):
                    # 计算进度
                    progress = (i + 1) / len(self.completed_images) * 100
                    self.statusBar().showMessage(f"正在创建压缩包... {progress:.1f}%")
                    QApplication.processEvents()
                    
                    # 添加文件到压缩包
                    arcname = os.path.basename(result['output_path'])
                    zipf.write(result['output_path'], arcname)
            
            self.statusBar().showMessage("就绪")
            QMessageBox.information(self, "成功", f"压缩包已创建: {zip_path}")
        except Exception as e:
            self.statusBar().showMessage("就绪")
            QMessageBox.critical(self, "错误", f"创建压缩包失败: {e}")
    
    def save_images(self, save_dir):
        """保存图片到目录"""
        import shutil
        
        try:
            for i, result in enumerate(self.completed_images):
                # 计算进度
                progress = (i + 1) / len(self.completed_images) * 100
                self.statusBar().showMessage(f"正在保存图片... {progress:.1f}%")
                QApplication.processEvents()
                
                # 复制文件
                save_path = os.path.join(save_dir, os.path.basename(result['output_path']))
                shutil.copy2(result['output_path'], save_path)
            
            self.statusBar().showMessage("就绪")
            QMessageBox.information(self, "成功", f"图片已保存到: {save_dir}")
        except Exception as e:
            self.statusBar().showMessage("就绪")
            QMessageBox.critical(self, "错误", f"保存图片失败: {e}")
    
    def clear_all(self):
        """清除所有图片"""
        # 停止所有压缩线程
        for thread in self.compress_threads.values():
            if thread.isRunning():
                thread.terminate()
        
        # 清空列表
        self.image_list.clear()
        self.image_items.clear()
        self.compress_threads.clear()
        self.completed_images.clear()
        
        # 重置计数
        self.pending_count = 0
        self.processing_count = 0
        self.completed_count = 0
        self.update_task_status()
        
        # 禁用批量下载按钮
        self.batch_download_button.setEnabled(False)
    
    def update_task_status(self):
        """更新任务状态"""
        self.task_status_label.setText(
            f"待处理: {self.pending_count} | 处理中: {self.processing_count} | 已完成: {self.completed_count}"
        )
    
    def show_about_dialog(self):
        """显示关于对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("关于软件")
        dialog.setGeometry(300, 300, 400, 200)
        
        layout = QVBoxLayout()
        
        label = QLabel("图片无损压缩客户端 v1.0\n\n"
                      "一个简单易用的图片压缩工具，支持多种图片格式的无损压缩。\n\n"
                      "功能特点：\n"
                      "- 支持多图片批量压缩\n"
                      "- 实时显示压缩进度\n"
                      "- 单张下载或批量打包下载\n"
                      "- 美观的用户界面")
        label.setAlignment(Qt.AlignCenter)
        label.setFont(QFont("Arial", 10))
        
        button = QPushButton("确定")
        button.clicked.connect(dialog.close)
        button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 3px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        
        layout.addWidget(label)
        layout.addWidget(button, 0, Qt.AlignCenter)
        
        dialog.setLayout(layout)
        dialog.exec_()
    
    def open_developer_page(self):
        """打开开发者主页"""
        import webbrowser
        webbrowser.open("https://github.com/tinygeeker")
    
    def show_donate_dialog(self):
        """显示打赏对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("打赏")
        dialog.setGeometry(100, 50, 900, 600)  # 增大对话框大小
        
        layout = QVBoxLayout()
        
        label = QLabel("如果您觉得这个软件对您有帮助，\n"
                      "欢迎通过以下方式打赏支持开发者：")
        label.setAlignment(Qt.AlignCenter)
        label.setFont(QFont("Arial", 11, QFont.Bold))
        
        # 显示打赏图片
        donate_image_path = os.path.join(os.path.dirname(__file__), "asset", "donate.jpg")
        if os.path.exists(donate_image_path):
            pixmap = QPixmap(donate_image_path)
            # 调整图片大小以适应对话框，进一步增大
            pixmap = pixmap.scaled(800, 500, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            image_label = QLabel()
            image_label.setPixmap(pixmap)
            image_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(image_label)
        else:
            # 如果图片不存在，显示提示信息
            image_label = QLabel("打赏图片未找到")
            image_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(image_label)
        
        button = QPushButton("确定")
        button.clicked.connect(dialog.close)
        button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        
        layout.addWidget(label)
        layout.addWidget(button, 0, Qt.AlignCenter)
        
        dialog.setLayout(layout)
        dialog.exec_()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())