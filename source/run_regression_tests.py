"""CG 算法回归测试脚本。

读取目录下所有 input_*.txt 测试用例，用 cg_cli.py 批量执行并生成 BMP 输出，
然后校验输出图像（非空、尺寸有效），最后生成 HTML/Markdown 双格式报告。

用途：每次修改算法实现后运行，确保已有用例的输出不退化。
"""

import argparse
import html
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

import cg_algorithms as alg


# 报告中算法列按此顺序展示，保持一致性
ALGORITHM_ORDER = [
    'DDA',
    'Bresenham',
    'Bezier',
    'B-spline',
    'Ellipse',
    'Cohen-Sutherland',
    'Liang-Barsky',
]


def count_nonwhite_pixels(path):
    """统计图像中非白色像素数，用于快速判断输出是否为空。"""
    image = Image.open(path).convert('RGB')
    data = image.tobytes()
    nonwhite = 0
    for index in range(0, len(data), 3):
        if data[index:index + 3] != b'\xff\xff\xff':
            nonwhite += 1
    return image.size, nonwhite


def analyze_input(input_path):
    """解析测试输入文件，统计各命令出现次数和涉及算法。"""
    command_counts = {}
    algorithms = set()
    for raw_line in input_path.read_text(encoding='utf-8').splitlines():
        parts = raw_line.strip().split()
        if not parts:
            continue
        command = parts[0]
        command_counts[command] = command_counts.get(command, 0) + 1
        if command in ('drawLine', 'drawPolygon', 'drawCurve', 'clip'):
            algorithms.add(parts[-1])
        elif command == 'drawEllipse':
            algorithms.add('Ellipse')
    return {
        'command_counts': command_counts,
        'algorithms': algorithms,
    }


def run_input(source_dir, input_path, output_root):
    """调用 cg_cli.py 执行单个测试输入文件，收集生成的 BMP 统计信息。"""
    # 计数 saveCanvas 命令条数以校验实际生成数
    expected_saves = sum(
        1
        for line in input_path.read_text(encoding='utf-8').splitlines()
        if line.strip().split()[:1] == ['saveCanvas']
    )
    if expected_saves == 0:
        return []

    target_dir = output_root / input_path.stem
    target_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [sys.executable, str(source_dir / 'cg_cli.py'), str(input_path), str(target_dir)],
        cwd=source_dir,
        check=True,
    )

    images = sorted(target_dir.glob('*.bmp'))
    if not images:
        raise RuntimeError(f'{input_path.name}: no BMP files generated')
    if len(images) != expected_saves:
        raise RuntimeError(f'{input_path.name}: expected {expected_saves} BMP files, got {len(images)}')

    stats = []
    for image_path in images:
        size, nonwhite = count_nonwhite_pixels(image_path)
        if size[0] <= 0 or size[1] <= 0:
            raise RuntimeError(f'{image_path.name}: invalid image size {size}')
        if nonwhite <= 0:
            raise RuntimeError(f'{image_path.name}: image is blank')
        stats.append((image_path.name, size, nonwhite, image_path))
    return stats


def format_command_counts(command_counts):
    """将命令计数格式化为易读字符串。"""
    if not command_counts:
        return 'None'
    return ', '.join(f'{name}: {command_counts[name]}' for name in sorted(command_counts))


def format_algorithms(algorithms):
    """按 ALGORITHM_ORDER 排序展示算法列表。"""
    ordered = [name for name in ALGORITHM_ORDER if name in algorithms]
    extra = sorted(name for name in algorithms if name not in ALGORITHM_ORDER)
    values = ordered + extra
    return ', '.join(values) if values else 'None'


def make_wu_comparison(report_dir):
    """生成 Bresenham vs Wu 反走样的对比图，嵌入报告用。"""
    image_path = report_dir / 'wu_vs_bresenham.png'
    image = Image.new('RGB', (760, 220), 'white')
    draw = ImageDraw.Draw(image)
    left_points = [[30, 160], [340, 40]]
    right_points = [[410, 160], [720, 40]]
    for x, y in alg.draw_line(left_points, 'Bresenham'):
        draw.point((x, y), fill=(25, 25, 25))
    for x, y, intensity in alg.draw_line_wu(right_points):
        color = tuple(int(255 - (255 - base) * intensity) for base in (30, 90, 210))
        draw.point((x, y), fill=color)
    draw.text((30, 12), 'Bresenham', fill=(25, 25, 25))
    draw.text((410, 12), 'Wu anti-aliasing', fill=(25, 25, 25))
    image.save(image_path)
    return image_path


def write_reports(report_dir, all_results, wu_image):
    """生成 HTML 和 Markdown 两份回归测试报告。"""
    # 汇总所有测试文件涉及的全部算法，生成覆盖率表格
    aggregate_algorithms = set()
    for _input_name, _stats, metadata in all_results:
        aggregate_algorithms.update(metadata['algorithms'])

    html_lines = [
        '<!doctype html>',
        '<html><head><meta charset="utf-8"><title>CG Regression Report</title></head><body>',
        '<h1>CG Regression Report</h1>',
        '<h2>Algorithm Coverage</h2>',
        '<table border="1" cellspacing="0" cellpadding="6"><tr><th>Algorithm</th><th>Covered</th></tr>',
    ]
    md_lines = ['# CG Regression Report', '']
    md_lines.extend(['## Algorithm Coverage', '', '| Algorithm | Covered |', '|---|---|'])
    for algorithm in ALGORITHM_ORDER:
        covered = 'Yes' if algorithm in aggregate_algorithms else 'No'
        html_lines.append(
            f'<tr><td>{html.escape(algorithm)}</td><td>{covered}</td></tr>'
        )
        md_lines.append(f'| {algorithm} | {covered} |')
    html_lines.append('</table>')
    md_lines.append('')

    for input_name, stats, metadata in all_results:
        html_lines.append(f'<h2>{html.escape(input_name)}</h2>')
        md_lines.extend([f'## {input_name}', ''])
        command_summary = format_command_counts(metadata['command_counts'])
        algorithm_summary = format_algorithms(metadata['algorithms'])
        html_lines.append(f'<p><strong>Commands:</strong> {html.escape(command_summary)}</p>')
        html_lines.append(f'<p><strong>Algorithms:</strong> {html.escape(algorithm_summary)}</p>')
        md_lines.extend([
            f'Commands: `{command_summary}`',
            '',
            f'Algorithms: `{algorithm_summary}`',
            '',
        ])
        if not stats:
            html_lines.append('<p>Skipped: no saveCanvas command.</p>')
            md_lines.extend(['Skipped: no `saveCanvas` command.', ''])
            continue
        # 每张输出图像一行，含缩略图预览
        html_lines.append('<table border="1" cellspacing="0" cellpadding="6"><tr><th>Image</th><th>Size</th><th>Nonwhite Pixels</th><th>Preview</th></tr>')
        md_lines.append('| Image | Size | Nonwhite Pixels | Preview |')
        md_lines.append('|---|---:|---:|---|')
        for image_name, size, nonwhite, image_path in stats:
            rel_path = image_path.relative_to(report_dir)
            html_lines.append(
                f'<tr><td>{html.escape(image_name)}</td><td>{size[0]}x{size[1]}</td>'
                f'<td>{nonwhite}</td><td><img src="{html.escape(str(rel_path))}" width="260"></td></tr>'
            )
            md_lines.append(f'| {image_name} | {size[0]}x{size[1]} | {nonwhite} | ![]({rel_path}) |')
        html_lines.append('</table>')
        md_lines.append('')

    rel_wu = wu_image.relative_to(report_dir)
    html_lines.append('<h2>Bresenham vs Wu Anti-aliasing</h2>')
    html_lines.append(f'<p><img src="{html.escape(str(rel_wu))}" width="760"></p>')
    html_lines.append('</body></html>')
    md_lines.extend(['## Bresenham vs Wu Anti-aliasing', '', f'![]({rel_wu})', ''])

    (report_dir / 'report.html').write_text('\n'.join(html_lines), encoding='utf-8')
    (report_dir / 'report.md').write_text('\n'.join(md_lines), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description='Run CG CLI regression tests for all input_*.txt files.')
    parser.add_argument('--output-dir', help='Directory to keep generated BMP outputs.')
    parser.add_argument('--report-dir', help='Directory to write report.html, report.md, and generated images.')
    args = parser.parse_args()

    source_dir = Path(__file__).resolve().parent
    input_files = sorted(source_dir.glob('input_*.txt'))
    if not input_files:
        raise RuntimeError(f'No input_*.txt files found in {source_dir}')

    report_dir = Path(args.report_dir).resolve() if args.report_dir else None
    if report_dir is not None:
        report_dir.mkdir(parents=True, exist_ok=True)
        output_root = Path(args.output_dir).resolve() if args.output_dir else report_dir / 'outputs'
        output_root.mkdir(parents=True, exist_ok=True)
        cleanup = None
    elif args.output_dir:
        output_root = Path(args.output_dir).resolve()
        output_root.mkdir(parents=True, exist_ok=True)
        cleanup = None
    else:
        # 未指定任何输出目录时，用临时目录（用完自动清理）
        cleanup = tempfile.TemporaryDirectory(prefix='cg_regression_')
        output_root = Path(cleanup.name)

    try:
        total_images = 0
        all_results = []
        for input_path in input_files:
            metadata = analyze_input(input_path)
            stats = run_input(source_dir, input_path, output_root)
            all_results.append((input_path.name, stats, metadata))
            if not stats:
                print(f'{input_path.name}: skipped (no saveCanvas command)')
                continue
            total_images += len(stats)
            print(f'{input_path.name}: {len(stats)} image(s)')
            for image_name, size, nonwhite, _image_path in stats:
                print(f'  {image_name}: size={size[0]}x{size[1]}, nonwhite={nonwhite}')
        if report_dir is not None:
            wu_image = make_wu_comparison(report_dir)
            write_reports(report_dir, all_results, wu_image)
            print(f'Report written: {report_dir / "report.html"}')
            print(f'Report written: {report_dir / "report.md"}')
        if cleanup is None:
            print(f'OK: {len(input_files)} input file(s), {total_images} image(s), output={output_root}')
        else:
            print(f'OK: {len(input_files)} input file(s), {total_images} image(s), temporary output removed')
    finally:
        if cleanup is not None:
            cleanup.cleanup()


if __name__ == '__main__':
    main()