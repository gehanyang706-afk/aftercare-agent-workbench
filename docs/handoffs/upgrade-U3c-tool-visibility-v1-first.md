# U3c 首次真实小批交接

固定train96×官方/候选各一次已结束，详细见 ../benchmarks/reports/U3c-tool-visibility-v1-first.md。
基线0（仅改地址，误判pending商品必须送达后再换）；候选1（地址+商品均完成）。均USER_STOP正常评分，无硬限/unknown。
34HTTP，159642输入+4948输出=164590Token，episode累计166.12秒；Agent分别64655/83082，候选多28.50%，没有同成功路径节省证据。
候选12次schema选择匹配、fallback0、未暴露提议0、工具错误0；同历史补回全目录后字节差14.30%，非Token收益。
0截断；候选1段冗长解释及1处到账措辞风险，未改输出或评分。
真实账本272请求/996369Token，cap仍2000000，可用835070，普通工作台仍离线。原始记录及历史成绩保留；本批授权结束，不自动重跑或扩到delivered/validation/Test。
