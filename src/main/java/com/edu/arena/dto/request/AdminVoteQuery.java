package com.edu.arena.dto.request;

import lombok.Data;
import org.springframework.format.annotation.DateTimeFormat;

import java.time.LocalDate;

/**
 * 后台投票记录查询参数。
 *
 * <p>通过 {@code @ModelAttribute} 绑定 query string。</p>
 */
@Data
public class AdminVoteQuery {

    private Integer page = 1;
    private Integer size = 20;

    /** 按投票人 userId 过滤 */
    private Long userId;
    /** 按用户名模糊过滤（displayName 或 username 任一命中） */
    private String keyword;
    /** 按对战 id 精确过滤 */
    private Long battleId;

    /** 起止日期（YYYY-MM-DD，闭区间，含当日全天） */
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate startDate;
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate endDate;
}
