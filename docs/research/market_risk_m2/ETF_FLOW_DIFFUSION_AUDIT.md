# ETF扩散审计
- G1 breadth_out 在聚合parquet中为全NaN（R3已知缺陷：G1无基金级成员标签）→ 本研究**剔除该特征**，不再填零。
- 扩散代理：breadth_out仅存在于分组级；扩散程度以G1/G2/G3深度与速度的方向一致性近似（M2_TEMPORAL_FEATURES中三组均有depth/vel20）。
- F模型ETF输入限定 {g1_depth, g1_ddur, g1_vel20} 三特征并按训练p1-p99截断OOD——仍出现train0.907→valid0.344的衰减，说明即便截断，符号/分布漂移仍在。
- 结论：扩散广度当前 **DATA_MISSING**，不可伪造。
