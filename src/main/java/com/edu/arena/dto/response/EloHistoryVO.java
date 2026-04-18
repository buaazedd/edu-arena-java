package com.edu.arena.dto.response;

import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

/**
 * ELO历史响应
 */
@Data
public class EloHistoryVO {

    private String modelName;
    private List<DataPoint> history;

    @Data
    public static class DataPoint {
        private BigDecimal score;
        private LocalDateTime time;
    }

}
