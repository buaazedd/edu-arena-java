package com.edu.arena.controller;

import com.edu.arena.common.result.Result;
import com.edu.arena.dto.response.LeaderboardVO;
import com.edu.arena.service.LeaderboardService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

/**
 * Leaderboard Controller
 */
@Tag(name = "Leaderboard API")
@RestController
@RequestMapping("/api/leaderboard")
@RequiredArgsConstructor
public class LeaderboardController {

    private final LeaderboardService leaderboardService;

    @Operation(summary = "Get leaderboard")
    @GetMapping
    public Result<List<LeaderboardVO>> getLeaderboard() {
        List<LeaderboardVO> list = leaderboardService.getLeaderboard();
        return Result.success(list);
    }

    @Operation(summary = "Get Elo history trend")
    @GetMapping("/elo_history")
    public Result<Map<String, List<Map<String, Object>>>> getEloHistory() {
        Map<String, List<Map<String, Object>>> history = leaderboardService.getEloHistory();
        return Result.success(history);
    }

}
