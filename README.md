# 鸭口选股 V5

> V5 策略：筛选 **V1 周线爆发** 与 **V4 鸭口选股** 的重合股票

## 策略说明

### V5 核心逻辑

**数据来源**：
- **V1**: 周线爆发策略 ([stock-picker](https://github.com/Jesse-J-whu/stock-picker))
- **V4**: 鸭口选股策略 ([stock-picker-v4](https://github.com/Jesse-J-whu/stock-picker-v4))

**筛选规则**：
```
V5 入选股票 = V1 选股结果 ∩ V4 选股结果
```

即：同时满足两种策略条件的股票，技术面呈现双重强势特征。

### 入选条件

1. 股票出现在 V1「周线爆发」的选股结果中
2. 股票同时出现在 V4「鸭口选股」的选股结果中
3. 取两者代码交集，保留完整的技术面数据

## 运行方式

```bash
pip install -r requirements.txt
python strategy.py
```

结果输出到：
- `docs/index.html` - GitHub Pages 展示页面
- `docs/data.json` - 原始数据 JSON

## 自动运行

通过 GitHub Actions，每天定时自动运行：

| 时间 (北京时间) | 说明 |
|----------------|------|
| 16:30 | 自动获取 V1、V4 最新结果并计算交集 |

**注意**：由于 GitHub Actions schedule 有延迟，实际运行时间可能在 16:30 ~ 18:00 之间。

## 数据展示

V5 结果页面展示：
- **重合股票数量**：同时满足两种策略的股票数
- **V1 技术面数据**：涨跌幅、成交量等
- **V4 技术面数据**：BOLL、MACD、OBV、DMA、AMO、KDJ 等六指标详情

## 在线访问

- **V5 结果页面**: https://jesse-j-whu.github.io/stock-picker-v5/
- **V1 策略页面**: https://jesse-j-whu.github.io/stock-picker/
- **V4 策略页面**: https://jesse-j-whu.github.io/stock-picker-v4/

## 免责声明

本项目仅为量化策略研究与学习，**不构成任何投资建议**。股市有风险，投资需谨慎。
