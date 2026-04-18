package com.edu.arena.service;

import com.edu.arena.dto.response.LeaderboardVO;

import java.util.List;
import java.util.Map;

/**
 * Leaderboard Service Interface
 */
public interface LeaderboardService {

    /**
     * Get leaderboard
     */
    List<LeaderboardVO> getLeaderboard();

    /**
     * Refresh cache
     */
    void refreshCache();

    /**
     * Get Elo history trend for all models
     */
    Map<String, List<Map<String, Object>>> getEloHistory();

}
