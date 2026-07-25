# 财经热搜 TOP 10 — 云端定时任务

每天 10:00 / 15:00（北京时间）自动抓取 tophub.today 全平台财经热搜，聚类合并，生成 HTML 报告并发送邮件。

## 工作原理

```
GitHub Actions (cron: 2:00 & 7:00 UTC)
  ↓
抓取 tophub.today/c/finance
  ↓
跨平台话题聚类 (jieba TF-IDF + Jaccard)
  ↓
智能模板生成报告 (HTML)
  ↓
部署 GitHub Pages + 发送 QQ 邮件
```

## 设置邮件

1. 登录 QQ 邮箱 → 设置 → 账户 → POP3/SMTP 服务 → 开启 → 获取授权码
2. 在 GitHub 仓库 Settings → Secrets and variables → Actions → New repository secret：
   - Name: `QQ_MAIL_AUTH_CODE`
   - Value: 刚才获取的授权码

## 手动触发

Actions → 每日财经热搜 TOP 10 → Run workflow

## 报告地址

`https://tommywoo626626-prog.github.io/finance-tophub-cloud/`
