from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import os
import argparse
from collections import deque
from typing import Set, List, Dict, Optional
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed


class DocsCrawler:
    """华为文档递归爬虫"""

    def __init__(self, base_url: str, output_dir: str = None, save_format: str = None, max_workers: int = 3, max_retries: int = 3, retry_delay: int = 2):
        """
        初始化爬虫

        Args:
            base_url: 起始URL
            output_dir: 保存目录
            save_format: 保存格式，可选值: None（不保存）, "html", "markdown", "both"
            max_workers: 最大线程数（默认3）
            max_retries: 最大重试次数（默认3）
            retry_delay: 重试延迟秒数（默认2）
        """
        self.base_url = base_url
        self.visited: Set[str] = set()  # 已访问URL
        self.queue: deque = deque()     # 待访问队列
        self.results: List[Dict] = []   # 爬取结果
        self.save_format = save_format  # 保存格式
        self.max_workers = max_workers  # 最大线程数
        self.max_retries = max_retries  # 最大重试次数
        self.retry_delay = retry_delay  # 重试延迟

        # 线程锁
        self.lock = threading.Lock()
        self.queue_lock = threading.Lock()

        # 输出目录
        if output_dir is None:
            output_dir = os.path.join(os.path.dirname(__file__), "docs")
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def fetch_html(self, url: str) -> str:
        """爬取单个页面的HTML（带重试机制）"""
        for attempt in range(self.max_retries):
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()
                    page.goto(url, wait_until="networkidle", timeout=60000)
                    html = page.content()
                    browser.close()
                    return html
            except Exception as e:
                if attempt < self.max_retries - 1:
                    print(f"  -> 第{attempt + 1}次尝试失败: {e}，{self.retry_delay}秒后重试...")
                    time.sleep(self.retry_delay)
                else:
                    raise Exception(f"重试{self.max_retries}次后仍失败: {e}")

    def parse_html(self, html: str, url: str) -> Dict:
        """解析HTML，提取标题、链接等信息"""
        soup = BeautifulSoup(html, "html.parser")

        # 提取标题
        title_elem = soup.find("h1", class_=lambda c: c and "doc-title" in str(c).split())
        title = title_elem.get_text(strip=True) if title_elem else "无标题"
        content_div = soup.find("div", class_=lambda c: c and "document-content-html" in str(c).split())

        # 提取描述（第一个段落文本）
        description = ""
        if content_div:
            first_p = content_div.find("p")
            if first_p:
                desc_text = first_p.get_text(strip=True)
                # 限制描述长度为200字符
                description = desc_text[:200] + "..." if len(desc_text) > 200 else desc_text

        # 提取核心内容区域的链接
        links = []
        if content_div:
            for link in content_div.find_all("a", href=True):
                href = link["href"]
                text = link.get_text(strip=True)

                if not text:
                    continue

                # 过滤掉带锚点的链接（同页面跳转）
                if "#" in href:
                    continue

                # 补全链接
                if href.startswith("/"):
                    href = "https://developer.huawei.com" + href

                links.append({"text": text, "url": href})

        # 判断是否为纯链接页面（非链接文本少于200字符）
        content_text = ""
        if content_div:
            # 移除所有链接标签后获取纯文本
            for a in content_div.find_all("a"):
                a.decompose()
            content_text = content_div.get_text(strip=True)
        is_links_only = len(content_text) < 200
        return {
            "url": url,
            "title": title,
            "links": links,
            "html": html,
            "is_links_only": is_links_only,
            "description": description,
        }

    def html_to_markdown(self, html: str) -> str:
        """将HTML转换为Markdown格式"""
        soup = BeautifulSoup(html, "html.parser")

        # 提取标题
        title_elem = soup.find("h1", class_=lambda c: c and "doc-title" in str(c).split())
        title = title_elem.get_text(strip=True) if title_elem else "无标题"

        # 提取核心内容区域
        content_div = soup.find("div", class_=lambda c: c and "document-content-html" in str(c).split())
        if not content_div:
            return f"# {title}\n\n未找到内容"

        lines = [f"# {title}\n"]

        # 遍历内容区域的所有标签
        for elem in content_div.find_all(["h1", "h2", "h3", "h4", "p", "ul", "ol", "li", "pre", "code", "strong", "a", "table"]):
            # 跳过嵌套在父元素中的内容
            if any(parent in ["li", "p", "pre", "code", "td", "th"] for parent in [p.name for p in elem.parents]):
                continue

            tag = elem.name

            # 标题处理
            if tag in ["h2", "h3", "h4"]:
                # 移除13+等版本标记中的sup标签
                for sup in elem.find_all("sup"):
                    sup.extract()
                text = elem.get_text(strip=True)
                if not text:
                    continue
                level = "#" * (int(tag[1]))
                lines.append(f"\n{level} {text}\n")

            # 段落处理
            elif tag == "p":
                text = elem.get_text(strip=True)
                if text:
                    lines.append(f"\n{text}\n")

            # 列表处理
            elif tag == "ul":
                for li in elem.find_all("li", recursive=False):
                    li_text = li.get_text(strip=True)
                    if li_text:
                        lines.append(f"- {li_text}")
                lines.append("")
            elif tag == "ol":
                for i, li in enumerate(elem.find_all("li", recursive=False), 1):
                    li_text = li.get_text(strip=True)
                    if li_text:
                        lines.append(f"{i}. {li_text}")
                lines.append("")

            # 代码块处理 - 保留原始换行
            elif tag == "pre":
                code_elem = elem.find("code")
                if code_elem:
                    # 检查是否有行号列表
                    ol_list = code_elem.find("ol", class_="linenums")
                    if ol_list:
                        # 从li标签中逐行提取代码，保留原始空格
                        code_lines = []
                        for li in ol_list.find_all("li", recursive=False):
                            # 使用strip=False保留代码中的空格，然后手动去除首尾空白
                            line_text = li.get_text(strip=False).strip()
                            code_lines.append(line_text)
                        code_text = "\n".join(code_lines)
                    else:
                        # 没有行号，直接提取文本
                        code_text = code_elem.get_text(separator='\n')
                else:
                    # pre下没有code标签，检查是否有行号列表
                    ol_list = elem.find("ol", class_="linenums")
                    if ol_list:
                        code_lines = []
                        for li in ol_list.find_all("li", recursive=False):
                            line_text = li.get_text(strip=False).strip()
                            code_lines.append(line_text)
                        code_text = "\n".join(code_lines)
                    else:
                        code_text = elem.get_text(separator='\n')

                lines.append(f"\n```\n{code_text}\n```\n")

            # 行内代码
            elif tag == "code" and elem.parent.name != "pre":
                text = elem.get_text(strip=True)
                if text:
                    lines.append(f"`{text}`")

            # 表格处理
            elif tag == "table":
                table_lines = self._parse_table(elem)
                lines.extend(table_lines)

        # 清理多余的空行（连续超过2个空行压缩为2个）
        result = "\n".join(lines)
        import re
        result = re.sub(r'\n{4,}', '\n\n\n', result)

        return result.strip()

    def _parse_table(self, table_elem) -> List[str]:
        """解析HTML表格为Markdown格式"""
        lines = []

        # 获取表头
        thead = table_elem.find("thead")
        if not thead:
            # 尝试查找第一行作为表头
            tbody = table_elem.find("tbody")
            if tbody:
                first_row = tbody.find("tr")
                if first_row and "firstRow" in first_row.get("class", []):
                    thead_rows = [first_row]
                else:
                    thead_rows = []
            else:
                thead_rows = []
        else:
            thead_rows = thead.find_all("tr")

        if not thead_rows:
            return lines

        # 解析表头
        headers = []
        for th in thead_rows[0].find_all(["th", "td"]):
            header_text = th.get_text(strip=True)
            # 从colspan属性获取列宽信息（如果有）
            width = th.get("width", "")
            headers.append(header_text)

        if not headers:
            return lines

        # 构建表头行
        lines.append("| " + " | ".join(headers) + " |")
        # 构建分隔符行
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

        # 解析表体
        tbody = table_elem.find("tbody")
        if tbody:
            for tr in tbody.find_all("tr"):
                # 跳过作为表头的第一行（已在thead处理）
                if "firstRow" in tr.get("class", []):
                    continue

                cells = tr.find_all(["td", "th"])
                if not cells:
                    continue

                row_data = []
                for cell in cells:
                    cell_text = cell.get_text(strip=True)
                    row_data.append(cell_text)

                if row_data:
                    lines.append("| " + " | ".join(row_data) + " |")

        lines.append("")  # 表格后空行
        return lines

    def save_file(self, url: str, html: str) -> Dict[str, Optional[str]]:
        """根据save_format保存文件"""
        # 从URL生成文件名
        filename = url.split("/")[-1] or "index"
        safe_filename = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in filename)

        result = {"html": None, "markdown": None}

        if self.save_format in ["html", "both"]:
            html_path = os.path.join(self.output_dir, f"{safe_filename}.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)
            result["html"] = html_path

        if self.save_format in ["markdown", "both"]:
            markdown = self.html_to_markdown(html)
            md_path = os.path.join(self.output_dir, f"{safe_filename}.md")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(markdown)
            result["markdown"] = md_path

        return result

    def is_valid_url(self, url: str) -> bool:
        """判断URL是否属于同一章节（只爬取harmonyos-references文档）"""
        return "/doc/harmonyos-references/" in url and "#" not in url

    def crawl_single_url(self, url: str) -> Optional[Dict]:
        """爬取单个URL（线程安全）"""
        # 检查是否已访问
        with self.lock:
            if url in self.visited:
                return None
            self.visited.add(url)

        if not self.is_valid_url(url):
            return None

        print(f"[线程{threading.current_thread().name}] 正在爬取: {url}")

        try:
            # 爬取并解析
            html = self.fetch_html(url)
            parsed = self.parse_html(html, url)

            # 保存文件
            filepaths = self.save_file(url, html)
            print(f"  -> 标题: {parsed['title']}")

            if filepaths["html"]:
                print(f"  -> HTML: {filepaths['html']}")
            if filepaths["markdown"]:
                print(f"  -> Markdown: {filepaths['markdown']}")

            # 保存结果
            result = {
                "url": url,
                "title": parsed["title"],
                "filepaths": filepaths,
                "links": parsed["links"],
                "description": parsed.get("description", "")
            }

            with self.lock:
                self.results.append(result)

            # 只有纯链接页面才将新链接加入队列
            new_links = []
            with self.queue_lock:
                for link in parsed["links"]:
                    link_url = link["url"]
                    if link_url not in self.visited and parsed.get("is_links_only", False):
                        self.queue.append(link_url)
                        new_links.append(link_url)

            if new_links:
                print(f"  -> [纯链接页面] 新增 {len(new_links)} 个链接到队列")

            return result

        except Exception as e:
            print(f"  -> 错误: {e}")
            return None

    def crawl(self):
        """开始多线程BFS递归爬取"""
        # 将起始URL加入队列
        with self.queue_lock:
            self.queue.append(self.base_url)

        with ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="Crawler") as executor:
            futures = []

            while True:
                url = None
                with self.queue_lock:
                    if self.queue:
                        url = self.queue.popleft()

                if url is None:
                    # 检查是否还有任务在执行
                    if any(f.running() for f in futures):
                        time.sleep(0.5)
                        continue
                    else:
                        break

                # 动态调整线程数：当队列大于5时，使用最大线程数
                current_queue_size = len(self.queue)
                active_threads = sum(1 for f in futures if f.running())

                # 提交任务
                future = executor.submit(self.crawl_single_url, url)
                futures.append(future)

                print(f"队列状态: {current_queue_size} 待处理, {active_threads} 活跃线程")

                # 清理已完成的任务
                futures = [f for f in futures if not f.done()]

        return self.results

    def get_summary(self) -> str:
        """获取爬取摘要"""
        lines = [
            f"\n{'=' * 60}",
            f"爬取完成统计",
            f"{'=' * 60}",
            f"总计爬取: {len(self.results)} 个页面",
            f"",
            f"文档列表:",
        ]

        for i, item in enumerate(self.results, 1):
            lines.append(f"\n{i}. {item['title']}")
            lines.append(f"   URL: {item['url']}")

            if item['filepaths']['html']:
                lines.append(f"   HTML: {item['filepaths']['html']}")
            if item['filepaths']['markdown']:
                lines.append(f"   Markdown: {item['filepaths']['markdown']}")

            if item['links']:
                lines.append(f"   包含 {len(item['links'])} 个子链接:")

        return "\n".join(lines)

    def generate_catalog(self) -> str:
        """生成文档目录（Markdown格式）"""
        lines = [
            "# 文档目录\n",
            f"本文档汇总了所有爬取的华为 HarmonyOS 文档，共计 {len(self.results)} 篇。\n",
            "---\n",
        ]

        for i, item in enumerate(self.results, 1):
            # 标题和链接
            title = item['title']
            url = item['url']

            # 检查是否有本地的 Markdown 文件
            if item['filepaths'].get('markdown'):
                md_filename = os.path.basename(item['filepaths']['markdown'])
                lines.append(f"{i}. [{title}]({md_filename})")
            else:
                lines.append(f"{i}. {title}")

            # 添加描述
            description = item.get('description', '')
            if description:
                lines.append(f"   - **描述**: {description}")

            # 添加原始链接
            lines.append(f"   - **原文**: [{url}]({url})")

            lines.append("")  # 空行分隔

        return "\n".join(lines)

    def save_catalog(self):
        """保存目录文档到文件"""
        catalog_content = self.generate_catalog()
        catalog_path = os.path.join(self.output_dir, "CATALOG.md")

        with open(catalog_path, "w", encoding="utf-8") as f:
            f.write(catalog_content)

        print(f"\n📚 目录文档已生成: {catalog_path}")
        return catalog_path


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description="华为文档递归爬虫",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 爬取 accessibility-api 章节，保存为 Markdown（3个线程）
  python GetDoc.py https://developer.huawei.com/consumer/cn/doc/harmonyos-references/accessibility-api -f markdown

  # 指定输出目录和5个线程加速
  python GetDoc.py <URL> -o ./output -f both -w 5
 
  # 只爬取不保存
  python GetDoc.py <URL> -f none
        """
    )

    parser.add_argument(
        "url",
        help="起始URL（华为文档链接）"
    )

    parser.add_argument(
        "-o", "--output",
        dest="output_dir",
        help="输出目录（默认: ./docs）",
        default=None
    )

    parser.add_argument(
        "-f", "--format",
        dest="save_format",
        choices=["none", "html", "markdown", "both"],
        help="保存格式: none（不保存）、html、markdown、both（默认: markdown）",
        default="markdown"
    )

    parser.add_argument(
        "-w", "--workers",
        dest="max_workers",
        type=int,
        help="最大线程数（默认: 3）",
        default=3
    )

    parser.add_argument(
        "-r", "--retries",
        dest="max_retries",
        type=int,
        help="最大重试次数（默认: 3）",
        default=3
    )

    parser.add_argument(
        "--retry-delay",
        dest="retry_delay",
        type=int,
        help="重试延迟秒数（默认: 2）",
        default=2
    )

    args = parser.parse_args()

    # 转换 save_format
    save_format = None if args.save_format == "none" else args.save_format

    # 创建爬虫实例
    crawler = DocsCrawler(args.url, output_dir=args.output_dir, save_format=save_format, max_workers=args.max_workers, max_retries=args.max_retries, retry_delay=args.retry_delay)

    # 开始爬取
    crawler.crawl()

    # 打印摘要
    print(crawler.get_summary())

    # 生成并保存目录文档
    if crawler.save_format:  # 只有保存了文件时才生成目录
        crawler.save_catalog()


def run():
    """测试函数 - 直接运行此文件时执行"""
    # 测试配置
    test_url = "https://developer.huawei.com/consumer/cn/doc/harmonyos-references/arkts-apis-image-auxiliarypicture"

    # 多线程爬取，最多5个线程
    crawler = DocsCrawler(test_url, save_format="markdown", max_workers=5)
    crawler.crawl()
    print(crawler.get_summary())
    crawler.save_catalog()


if __name__ == "__main__":
    # 如果有命令行参数，使用命令行模式
    import sys
    if len(sys.argv) > 1:
        main()
    else:
        # 否则运行测试
        run()

        