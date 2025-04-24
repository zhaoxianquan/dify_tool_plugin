from collections.abc import Generator
from typing import Any, Dict, List
import os
import zipfile
import tempfile
import shutil
import rarfile
import py7zr
import tarfile
from pathlib import Path
from dify_plugin.file.file import File
from pathlib import Path
from tempfile import NamedTemporaryFile
import pandas as pd

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeServerUnavailableError
from tools.utils.mimetype_utils import MimeType


class UnzipFileTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        # 获取压缩文件参数
        file_data = tool_parameters.get('file')

        # 检查是否提供了压缩文件
        if not file_data:
            error_msg = "错误: 未提供压缩文件"
            yield self.create_text_message(error_msg)
            raise InvokeServerUnavailableError(error_msg)

        if not isinstance(file_data, File):
            error_msg = f"错误: 传入的对象不是 dify_plugin.file.file.File 类型，而是 {type(file_data)} 类型。"
            yield self.create_text_message(error_msg)
            raise InvokeServerUnavailableError(error_msg)
            
        # 创建临时目录用于解压
        temp_dir = tempfile.mkdtemp()
        temp_file_path = os.path.join(temp_dir, "compressed_file")

        try:
            # 直接通过 blob 属性获取文件内容（类型为 bytes）
            file_content = file_data.blob  # 关键修正点：使用 blob 而非 read()

            # 写入临时文件（无需类型转换，blob 已为 bytes）
            with open(temp_file_path, 'wb') as f:
                f.write(file_content)

            # 检测文件类型并解压
            file_type = self._detect_file_type(temp_file_path)
            extract_dir = os.path.join(temp_dir, "extracted")
            os.makedirs(extract_dir, exist_ok=True)
            
            if file_type == "zip":
                self._extract_zip(temp_file_path, extract_dir)
            elif file_type == "rar":
                self._extract_rar(temp_file_path, extract_dir)
            elif file_type == "7z":
                self._extract_7z(temp_file_path, extract_dir)
            elif file_type == "tar" or file_type == "tar.gz" or file_type == "tar.bz2":
                self._extract_tar(temp_file_path, extract_dir)
            else:
                file_info = self._get_file_info(temp_file_path)
                error_msg = f"错误: 不支持的压缩文件格式: {file_type}\n文件信息: {file_info}"
                yield self.create_text_message(error_msg)
                raise InvokeServerUnavailableError(error_msg)

            # 获取文件列表并返回
            file_list = self._get_file_list(extract_dir)
            for file_info in file_list:
                if file_info["type"] == "file":
                    file_path = os.path.join(extract_dir, file_info["path"])
                    file_name = file_info["name"]
                    yield self.create_blob_message(blob=Path(file_path).read_bytes(), meta={"mime_type": MimeType.XLSX,"filename": file_name})
                else:
                    yield self.create_text_message(f"跳过目录: {file_info['name']}")
                
            yield self.create_text_message(f"共 {len(file_list)} 个文件解压成功，已返回文件列表。")

        except Exception as e:
            error_msg = f"解压失败: {str(e)}"
            yield self.create_text_message(error_msg)
            raise InvokeServerUnavailableError(error_msg)
        finally:
            # 清理临时目录
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _detect_file_type(self, file_path: str) -> str:
        """检测压缩文件类型"""
        # 获取文件名和扩展名用于辅助判断
        file_name = os.path.basename(file_path).lower()

        # 检查文件头部特征 - 读取更多字节以增强识别能力
        with open(file_path, 'rb') as f:
            header = f.read(20)  # 增加读取的字节数

        # ZIP文件头: 50 4B 03 04 (PK..)
        if header.startswith(b'PK\x03\x04') or header.startswith(b'PK\x05\x06') or header.startswith(b'PK\x07\x08'):
            return "zip"
        # RAR文件头: 52 61 72 21 1A 07 (Rar!..)
        elif header.startswith(b'Rar!\x1a\x07'):
            return "rar"
        # 7Z文件头: 37 7A BC AF 27 1C (7z...)
        elif header.startswith(b'7z\xbc\xaf\x27\x1c'):
            return "7z"
        # GZIP文件头: 1F 8B (..)
        elif header.startswith(b'\x1f\x8b'):
            if file_name.endswith(".tar.gz") or file_name.endswith(".tgz"):
                return "tar.gz"
            else:
                return "gzip"
        # BZ2文件头: 42 5A 68 (BZh)
        elif header.startswith(b'BZh'):
            if file_name.endswith(".tar.bz2") or file_name.endswith(".tbz2"):
                return "tar.bz2"
            else:
                return "bz2"
        # TAR文件: 检查文件扩展名和文件头
        # 标准TAR文件没有固定的魔数，但通常在偏移257处有"ustar"
        elif file_name.endswith(".tar") or (len(header) > 257 and b'ustar' in header[257:262]):
            return "tar"
        elif file_name.endswith(".tar.gz") or file_name.endswith(".tgz"):
            return "tar.gz"
        elif file_name.endswith(".tar.bz2") or file_name.endswith(".tbz2"):
            return "tar.bz2"
        # 通过文件扩展名判断
        elif file_name.endswith(".zip"):
            return "zip"
        elif file_name.endswith(".rar"):
            return "rar"
        elif file_name.endswith(".7z"):
            return "7z"
        else:
            # 文件大小检查 - 过小的文件可能不是有效的压缩文件
            file_size = os.path.getsize(file_path)
            if file_size < 100:  # 如果文件太小，可能不是有效的压缩文件
                return "unknown"

            # 尝试通过zipfile库判断
            try:
                with zipfile.ZipFile(file_path, 'r') as zip_file:
                    # 检查文件是否至少包含一个条目
                    if zip_file.namelist():
                        return "zip"
            except zipfile.BadZipFile:
                pass
            except Exception as e:
                # 记录详细错误但继续尝试其他格式
                print(f"ZIP检测错误: {str(e)}")

            # 尝试通过rarfile库判断
            try:
                with rarfile.RarFile(file_path, 'r') as rar_file:
                    # 检查文件是否至少包含一个条目
                    if rar_file.namelist():
                        return "rar"
            except rarfile.NotRarFile:
                pass
            except Exception as e:
                print(f"RAR检测错误: {str(e)}")

            # 尝试通过py7zr库判断
            try:
                with py7zr.SevenZipFile(file_path, 'r') as sz_file:
                    # 检查文件是否至少包含一个条目
                    if list(sz_file.files()):
                        return "7z"
            except py7zr.Bad7zFile:
                pass
            except Exception as e:
                print(f"7Z检测错误: {str(e)}")

            # 尝试通过tarfile库判断
            try:
                with tarfile.open(file_path, 'r:*') as tar_file:
                    # 检查文件是否至少包含一个条目
                    if tar_file.getmembers():
                        return "tar"
            except tarfile.ReadError:
                pass
            except Exception as e:
                print(f"TAR检测错误: {str(e)}")

            # 尝试读取文件内容的更多部分进行深度检测
            try:
                with open(file_path, 'rb') as f:
                    content = f.read(4096)  # 读取更多内容进行分析

                    # 检查是否包含ZIP文件的中央目录结构特征
                    if b'PK\x01\x02' in content:
                        return "zip"

                    # 检查是否包含RAR文件的卷头特征
                    if b'\x52\x61\x72\x21' in content:
                        return "rar"
            except Exception as e:
                print(f"深度检测错误: {str(e)}")

            # 无法识别文件类型，返回详细信息
            return "unknown"

    def _extract_zip(self, file_path: str, extract_dir: str) -> None:
        """解压ZIP文件"""
        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            # 检查是否有密码保护
            for info in zip_ref.infolist():
                if info.flag_bits & 0x1:
                    raise Exception("ZIP文件有密码保护，无法解压")
            # 解压所有文件
            zip_ref.extractall(extract_dir)

    def _extract_rar(self, file_path: str, extract_dir: str) -> None:
        """解压RAR文件"""
        with rarfile.RarFile(file_path, 'r') as rar_ref:
            # 检查是否有密码保护
            if rar_ref.needs_password():
                raise Exception("RAR文件有密码保护，无法解压")
            # 解压所有文件
            rar_ref.extractall(extract_dir)

    def _extract_7z(self, file_path: str, extract_dir: str) -> None:
        """解压7Z文件"""
        with py7zr.SevenZipFile(file_path, 'r') as sz_ref:
            # 检查是否有密码保护
            if sz_ref.needs_password():
                raise Exception("7Z文件有密码保护，无法解压")
            # 解压所有文件
            sz_ref.extractall(extract_dir)

    def _extract_tar(self, file_path: str, extract_dir: str) -> None:
        """解压TAR文件(包括tar.gz和tar.bz2)"""
        with tarfile.open(file_path, 'r:*') as tar_ref:
            # 安全检查：防止路径遍历攻击
            def is_within_directory(directory, target):
                abs_directory = os.path.abspath(directory)
                abs_target = os.path.abspath(target)
                prefix = os.path.commonprefix([abs_directory, abs_target])
                return prefix == abs_directory

            def safe_extract(tar, path):
                for member in tar.getmembers():
                    member_path = os.path.join(path, member.name)
                    if not is_within_directory(path, member_path):
                        raise Exception("检测到路径遍历攻击尝试")
                    tar.extract(member, path)

            safe_extract(tar_ref, extract_dir)

    def _get_file_info(self, file_path: str) -> str:
        """获取文件的详细信息，用于错误诊断"""
        try:
            file_size = os.path.getsize(file_path)
            file_name = os.path.basename(file_path)

            # 读取文件头部
            with open(file_path, 'rb') as f:
                header_hex = f.read(16).hex()

            # 获取文件扩展名
            _, ext = os.path.splitext(file_path)

            return f"文件名: {file_name}, 大小: {file_size} 字节, 扩展名: {ext}, 文件头: {header_hex}"
        except Exception as e:
            return f"无法获取文件信息: {str(e)}"

    def _get_file_list(self, directory: str) -> List[Dict[str, Any]]:
        """获取解压后的文件列表"""
        file_list = []

        for root, dirs, files in os.walk(directory):
            # 处理文件
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, directory)
                file_size = os.path.getsize(file_path)
                file_info = {
                    "name": file,
                    "path": rel_path,
                    "size": file_size,
                    "type": "file"
                }
                # 使用create_blob_message包装文件内容
                # blob_message = self.create_blob_message(self, blob)
                file_list.append(file_info)

            # 处理目录
            for dir_name in dirs:
                dir_path = os.path.join(root, dir_name)
                rel_path = os.path.relpath(dir_path, directory)
                dir_info = {
                    "name": dir_name,
                    "path": rel_path,
                    "type": "directory"
                }
                file_list.append(dir_info)
        return file_list
