package com.edu.arena.controller;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.edu.arena.common.exception.BusinessException;
import com.edu.arena.common.result.Result;
import com.edu.arena.common.utils.UserContext;
import com.edu.arena.dto.request.CreateBattleRequest;
import com.edu.arena.dto.request.VoteRequest;
import com.edu.arena.dto.response.BattleHistoryVO;
import com.edu.arena.dto.response.BattleVO;
import com.edu.arena.dto.response.VoteResultVO;
import com.edu.arena.service.BattleService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

/**
 * 对战控制器
 */
@Tag(name = "对战接口")
@RestController
@RequiredArgsConstructor
public class BattleController {

    private final BattleService battleService;

    @Operation(summary = "创建对战")
    @PostMapping("/api/battle/create")
    public Result<Long> createBattle(@Valid @RequestBody CreateBattleRequest request) {
        Long userId = UserContext.getUserId();
        if (userId == null) {
            throw new BusinessException(401, "请先登录");
        }
        Long battleId = battleService.createBattle(userId, request);
        return Result.success("对战已创建", battleId);
    }

    @Operation(summary = "同步生成对战内容")
    @GetMapping("/api/battle/{id}/generate")
    public Result<BattleVO> generateBattle(@PathVariable Long id) {
        BattleVO vo = battleService.generateBattle(id);
        return Result.success(vo);
    }

    @Operation(summary = "获取对战详情")
    @GetMapping("/api/battle/{id}")
    public Result<BattleVO> getBattle(@PathVariable Long id) {
        BattleVO vo = battleService.getBattleDetail(id);
        return Result.success(vo);
    }

    @Operation(summary = "投票")
    @PostMapping("/api/battle/{id}/vote")
    public Result<VoteResultVO> vote(@PathVariable Long id, @Valid @RequestBody VoteRequest request) {
        Long userId = UserContext.getUserId();
        if (userId == null) {
            throw new BusinessException(401, "请先登录");
        }
        VoteResultVO result = battleService.vote(userId, id, request);
        return Result.success(result);
    }

    @Operation(summary = "获取对战历史")
    @GetMapping("/api/battles/history")
    public Result<IPage<BattleHistoryVO>> getBattleHistory(
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int size) {
        IPage<BattleHistoryVO> history = battleService.getBattleHistory(page, size);
        return Result.success(history);
    }

}
