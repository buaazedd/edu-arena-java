package com.edu.arena.dto.request;

import lombok.Data;

import java.time.LocalDate;

/**
 * 偏好数据集导出查询参数。
 *
 * <p>所有字段均可空。空值等价于不过滤；脏数据（status != voted）由服务层强制过滤。</p>
 */
@Data
public class ExportQuery {

    /**
     * 总体获胜方过滤：A / B / tie。null 表示不过滤。
     */
    private String winner;

    /**
     * 限定参与方（A 或 B 任一匹配即纳入）。可传模型主键 ID（推荐）或 model_id 字符串。
     * null 表示不过滤。
     */
    private String modelId;

    /**
     * 起始日期（按 battles.created_at 闭区间）。null 表示不限。
     */
    private LocalDate startDate;

    /**
     * 截止日期（按 battles.created_at 闭区间，内部下推到次日 00:00 不含）。null 表示不限。
     */
    private LocalDate endDate;

    /**
     * 仅导出指定 battle_id（调试/补刀用）。
     */
    private Long battleId;

    /**
     * 是否在 ZIP 中包含 images/ 目录。默认 true。
     */
    private Boolean includeImages = Boolean.TRUE;

    /**
     * 最大导出条数（防止一次性导出过大）。<=0 或 null 表示不限。
     */
    private Integer limit;
}
