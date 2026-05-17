"""
鸭口选股策略 V5
========================
V5 策略逻辑：筛选 V1（周线爆发）和 V4（鸭口选股）重合的股票

策略说明：
  - V1: 周线爆发策略（https://github.com/Jesse-J-whu/stock-picker）
  - V4: 鸭口选股策略（https://github.com/Jesse-J-whu/stock-picker-v4）
  - V5: 取 V1 和 V4 选股结果的交集

入选条件：
  1. 股票同时出现在 V1 和 V4 的选股结果中
  2. 保留两只策略的详细数据供参考
"""

import json
import requests
from datetime import datetime
from jinja2 import Template

# ============================================================
# HTTP 基础设施
# ============================================================

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# ============================================================
# 数据源配置
# ============================================================

V1_DATA_URL = "https://jesse-j-whu.github.io/stock-picker/data.json"
V4_DATA_URL = "https://jesse-j-whu.github.io/stock-picker-v4/data.json"

# ============================================================
# 数据获取层
# ============================================================

def fetch_stock_data(url, source_name):
    """从指定URL获取选股数据"""
    print(f"[1/3] 获取 {source_name} 选股结果...")
    try:
        resp = SESSION.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        print(f"  ✓ {source_name}: 获取到 {data.get('count', 0)} 只股票")
        return data
    except Exception as e:
        print(f"  ✗ 获取 {source_name} 数据失败: {e}")
        return None

# ============================================================
# 策略核心：求交集
# ============================================================

def find_intersection(v1_data, v4_data):
    """
    找出 V1 和 V4 重合的股票
    以股票代码(code)为唯一标识进行匹配
    """
    print("\n[2/3] 计算 V1 和 V4 的重合股票...")
    
    if not v1_data or not v4_data:
        print("  ✗ 数据不完整，无法计算交集")
        return []
    
    # 提取 V1 股票代码集合
    v1_stocks = v1_data.get('stocks', [])
    v1_codes = {stock['code'] for stock in v1_stocks}
    
    # 提取 V4 股票代码集合
    v4_stocks = v4_data.get('stocks', [])
    v4_codes = {stock['code'] for stock in v4_stocks}
    
    # 计算交集
    intersection_codes = v1_codes & v4_codes
    
    # 构建交集股票的详细信息
    intersection_stocks = []
    
    for code in intersection_codes:
        # 从 V1 查找股票信息
        v1_stock = next((s for s in v1_stocks if s['code'] == code), None)
        # 从 V4 查找股票信息
        v4_stock = next((s for s in v4_stocks if s['code'] == code), None)
        
        if v1_stock and v4_stock:
            merged_stock = {
                'code': code,
                'name': v1_stock.get('name', v4_stock.get('name', '')),
                # V1 数据
                'v1_price': v1_stock.get('price', 0),
                'v1_change_pct': v1_stock.get('change_pct', 0),
                'v1_volume': v1_stock.get('volume', 0),
                # V4 数据
                'v4_price': v4_stock.get('price', 0),
                'v4_change_pct': v4_stock.get('change_pct', 0),
                'v4_volume': v4_stock.get('volume', 0),
                # V4 详细条件
                'v4_detail': v4_stock.get('detail', {}),
            }
            intersection_stocks.append(merged_stock)
    
    # 按涨跌幅排序（V1 数据）
    intersection_stocks.sort(key=lambda x: x['v1_change_pct'], reverse=True)
    
    print(f"  ✓ 找到 {len(intersection_stocks)} 只重合股票")
    print(f"    V1 总数: {len(v1_stocks)}, V4 总数: {len(v4_stocks)}")
    
    return intersection_stocks

# ============================================================
# HTML 报告生成
# ============================================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>鸭口选股 V5 - V1 & V4 重合股筛选</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        h1 {
            color: #333;
            font-size: 32px;
            margin-bottom: 10px;
            text-align: center;
        }
        .subtitle {
            text-align: center;
            color: #666;
            font-size: 16px;
            margin-bottom: 30px;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 12px;
            text-align: center;
        }
        .stat-card h3 {
            font-size: 14px;
            font-weight: normal;
            margin-bottom: 10px;
            opacity: 0.9;
        }
        .stat-card .value {
            font-size: 28px;
            font-weight: bold;
        }
        .info-box {
            background: #f8f9fa;
            border-left: 4px solid #667eea;
            padding: 15px 20px;
            margin-bottom: 30px;
            border-radius: 8px;
        }
        .info-box h4 {
            color: #333;
            margin-bottom: 10px;
        }
        .info-box p {
            color: #666;
            line-height: 1.6;
        }
        .stock-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
            font-size: 14px;
        }
        .stock-table th {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px 10px;
            text-align: center;
            font-weight: 600;
            position: sticky;
            top: 0;
        }
        .stock-table td {
            padding: 12px 10px;
            text-align: center;
            border-bottom: 1px solid #e0e0e0;
        }
        .stock-table tr:hover { background: #f5f5f5; }
        .code { font-weight: 600; color: #667eea; }
        .name { font-weight: 500; }
        .up { color: #e74c3c; }
        .down { color: #27ae60; }
        .detail-cell {
            font-size: 12px;
            color: #666;
            max-width: 300px;
            text-align: left;
            line-height: 1.4;
        }
        .detail-cell span {
            display: inline-block;
            margin: 2px 4px;
            padding: 2px 6px;
            background: #f0f0f0;
            border-radius: 4px;
        }
        .badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 500;
        }
        .badge-success { background: #d4edda; color: #155724; }
        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: #666;
        }
        .empty-state h3 {
            font-size: 24px;
            margin-bottom: 10px;
        }
        footer {
            text-align: center;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #e0e0e0;
            color: #999;
            font-size: 12px;
        }
        footer a {
            color: #667eea;
            text-decoration: none;
        }
        footer a:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎯 鸭口选股 V5</h1>
        <p class="subtitle">V1 周线爆发 + V4 鸭口选股 · 重合股精选</p>
        
        <div class="stats">
            <div class="stat-card">
                <h3>更新时间</h3>
                <div class="value" style="font-size: 16px;">{{ update_time }}</div>
            </div>
            <div class="stat-card">
                <h3>重合股票数</h3>
                <div class="value">{{ count }}</div>
            </div>
            <div class="stat-card">
                <h3>V1 入选数</h3>
                <div class="value">{{ v1_count }}</div>
            </div>
            <div class="stat-card">
                <h3>V4 入选数</h3>
                <div class="value">{{ v4_count }}</div>
            </div>
        </div>
        
        <div class="info-box">
            <h4>📊 策略说明</h4>
            <p>
                <strong>V5 筛选逻辑：</strong>找出同时满足 V1「周线爆发」策略和 V4「鸭口选股」策略的股票。
                这些股票在技术面同时呈现两种强势特征，值得重点关注。<br><br>
                <strong>数据来源：</strong>
                <a href="https://jesse-j-whu.github.io/stock-picker/" target="_blank">V1 周线爆发</a> |
                <a href="https://jesse-j-whu.github.io/stock-picker-v4/" target="_blank">V4 鸭口选股</a>
            </p>
        </div>
        
        {% if stocks %}
        <table class="stock-table">
            <thead>
                <tr>
                    <th>排名</th>
                    <th>股票代码</th>
                    <th>股票名称</th>
                    <th>V1 涨跌幅</th>
                    <th>V4 涨跌幅</th>
                    <th>V4 技术面详情</th>
                </tr>
            </thead>
            <tbody>
                {% for stock in stocks %}
                <tr>
                    <td>{{ loop.index }}</td>
                    <td class="code">{{ stock.code }}</td>
                    <td class="name">{{ stock.name }}</td>
                    <td class="{% if stock.v1_change_pct > 0 %}up{% else %}down{% endif %}">
                        {{ "%.2f"|format(stock.v1_change_pct) }}%
                    </td>
                    <td class="{% if stock.v4_change_pct > 0 %}up{% else %}down{% endif %}">
                        {{ "%.2f"|format(stock.v4_change_pct) }}%
                    </td>
                    <td class="detail-cell">
                        {% for key, value in stock.v4_detail.items() %}
                        <span>{{ key }}: {{ value }}</span>
                        {% endfor %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <div class="empty-state">
            <h3>😔 暂无重合股票</h3>
            <p>当前 V1 和 V4 的选股结果没有交集，请稍后再试。</p>
        </div>
        {% endif %}
        
        <footer>
            <p>数据来源：腾讯财经 | 策略：鸭口选股 V5</p>
            <p>
                <a href="https://github.com/Jesse-J-whu/stock-picker-v5" target="_blank">GitHub 仓库</a> |
                <a href="data.json" target="_blank">原始数据 (JSON)</a>
            </p>
            <p style="margin-top: 10px; color: #ccc;">免责声明：本策略仅供学习研究，不构成投资建议</p>
        </footer>
    </div>
</body>
</html>
"""

def generate_report(stocks, v1_count, v4_count):
    """生成 HTML 报告"""
    print("\n[3/3] 生成 HTML 报告...")
    
    template = Template(HTML_TEMPLATE)
    html_content = template.render(
        update_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        count=len(stocks),
        v1_count=v1_count,
        v4_count=v4_count,
        stocks=stocks
    )
    
    # 确保 docs 目录存在
    os.makedirs('docs', exist_ok=True)
    
    # 保存 HTML
    with open('docs/index.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    # 保存 JSON 数据
    result_data = {
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'strategy': 'V5 - V1 & V4 重合股筛选',
        'v1_count': v1_count,
        'v4_count': v4_count,
        'count': len(stocks),
        'stocks': stocks
    }
    
    with open('docs/data.json', 'w', encoding='utf-8') as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)
    
    print(f"  ✓ HTML 报告: docs/index.html")
    print(f"  ✓ JSON 数据: docs/data.json")
    print(f"  ✓ 共 {len(stocks)} 只重合股票")

# ============================================================
# 主流程
# ============================================================

def main():
    print("=" * 60)
    print("鸭口选股 V5 - V1 & V4 重合股筛选")
    print("=" * 60)
    
    # 获取 V1 数据
    v1_data = fetch_stock_data(V1_DATA_URL, "V1 周线爆发")
    
    # 获取 V4 数据
    v4_data = fetch_stock_data(V4_DATA_URL, "V4 鸭口选股")
    
    # 计算交集
    intersection_stocks = find_intersection(v1_data, v4_data)
    
    # 获取统计数据
    v1_count = v1_data.get('count', 0) if v1_data else 0
    v4_count = v4_data.get('count', 0) if v4_data else 0
    
    # 生成报告
    generate_report(intersection_stocks, v1_count, v4_count)
    
    print("\n" + "=" * 60)
    print("✅ V5 选股完成！")
    print("=" * 60)

if __name__ == '__main__':
    import os
    main()
