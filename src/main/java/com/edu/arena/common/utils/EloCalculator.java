package com.edu.arena.common.utils;

import java.math.BigDecimal;
import java.math.RoundingMode;

/**
 * ELO计算工具类
 */
public class EloCalculator {

    private static final int DEFAULT_K = 32;

    /**
     * 计算新的ELO分数
     *
     * @param eloA   模型A当前ELO
     * @param eloB   模型B当前ELO
     * @param winner 获胜方: A, B, tie
     * @return [新ELO A, 新ELO B]
     */
    public static BigDecimal[] calculate(BigDecimal eloA, BigDecimal eloB, String winner) {
        return calculate(eloA, eloB, winner, DEFAULT_K);
    }

    /**
     * 计算新的ELO分数
     *
     * @param eloA   模型A当前ELO
     * @param eloB   模型B当前ELO
     * @param winner 获胜方: A, B, tie
     * @param k      K因子
     * @return [新ELO A, 新ELO B]
     */
    public static BigDecimal[] calculate(BigDecimal eloA, BigDecimal eloB, String winner, int k) {
        // 计算期望得分 - 使用Math.pow避免BigDecimal精度问题
        double diff = eloB.subtract(eloA).doubleValue();
        double expectedA = 1.0 / (1.0 + Math.pow(10.0, diff / 400.0));

        // 实际得分
        double actualA;
        switch (winner) {
            case "A":
                actualA = 1.0;
                break;
            case "B":
                actualA = 0.0;
                break;
            default: // tie
                actualA = 0.5;
        }

        // 计算新ELO
        double newEloA = eloA.doubleValue() + k * (actualA - expectedA);
        double newEloB = eloB.doubleValue() + k * ((1 - actualA) - (1 - expectedA));

        return new BigDecimal[]{
                BigDecimal.valueOf(newEloA).setScale(2, RoundingMode.HALF_UP),
                BigDecimal.valueOf(newEloB).setScale(2, RoundingMode.HALF_UP)
        };
    }

}
