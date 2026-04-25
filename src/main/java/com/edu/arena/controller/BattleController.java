package com.edu.arena.controller;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.edu.arena.common.exception.BusinessException;
import com.edu.arena.common.result.Result;
import com.edu.arena.common.utils.UserContext;
import com.edu.arena.dto.request.CreateBattleRequest;
import com.edu.arena.dto.request.VoteRequest;
import com.edu.arena.dto.response.BattleHistoryVO;
import com.edu.arena.dto.response.BattleVO;
import com.edu.arena.dto.response.BattleVoteVO;
import com.edu.arena.dto.response.VoteResultVO;
import com.edu.arena.service.BattleService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.Objects;

/**
 * 对战控制器
 */
@Tag(name = "对战接口")
@RestController
@RequiredArgsConstructor
public class BattleController {

    /** 投票人脱敏占位文案 */
    private static final String ANONYMOUS_VOTER = "匿名";

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
        // vo 可能来自缓存（本地/进程内命中时是同一引用），脱敏前先克隆 vote 子对象，
        // 避免跨角色、跨请求串号。外层 BattleVO 其他字段不需要改动，沿用引用即可。
        if (vo != null && vo.getVote() != null) {
            vo.setVote(cloneVote(vo.getVote()));
        }
        desensitizeBattleVote(vo);
        return Result.success(vo);
    }

    private BattleVoteVO cloneVote(BattleVoteVO src) {
        BattleVoteVO copy = new BattleVoteVO();
        copy.setVoteId(src.getVoteId());
        copy.setWinner(src.getWinner());
        copy.setDimTheme(src.getDimTheme());
        copy.setDimImagination(src.getDimImagination());
        copy.setDimLogic(src.getDimLogic());
        copy.setDimLanguage(src.getDimLanguage());
        copy.setDimWriting(src.getDimWriting());
        copy.setDimOverall(src.getDimOverall());
        copy.setDimThemeReason(src.getDimThemeReason());
        copy.setDimImaginationReason(src.getDimImaginationReason());
        copy.setDimLogicReason(src.getDimLogicReason());
        copy.setDimLanguageReason(src.getDimLanguageReason());
        copy.setDimWritingReason(src.getDimWritingReason());
        copy.setDimOverallReason(src.getDimOverallReason());
        copy.setVoterUserId(src.getVoterUserId());
        copy.setVoterUsername(src.getVoterUsername());
        copy.setVoterDisplayName(src.getVoterDisplayName());
        copy.setVoter(src.getVoter());
        copy.setCreatedAt(src.getCreatedAt());
        return copy;
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
        if (history != null && history.getRecords() != null) {
            history.getRecords().forEach(this::desensitizeHistoryVoter);
        }
        return Result.success(history);
    }

    // ================== 投票人脱敏 ==================
    // 规则：admin 看全部真实投票人；普通用户仅自己投票时显示真实信息，
    //       其他投票人统一显示为"匿名"，同时清除原始字段避免泄露。

    private void desensitizeBattleVote(BattleVO vo) {
        if (vo == null || vo.getVote() == null) {
            return;
        }
        BattleVoteVO voteVO = vo.getVote();
        if (isAdmin()) {
            // admin 保留原始字段；voter 用 displayName 优先 / username 兜底
            voteVO.setVoter(preferVoterName(voteVO));
            return;
        }
        Long currentUserId = UserContext.getUserId();
        if (currentUserId != null && Objects.equals(currentUserId, voteVO.getVoterUserId())) {
            voteVO.setVoter(preferVoterName(voteVO));
            return;
        }
        // 他人投票：脱敏
        voteVO.setVoter(ANONYMOUS_VOTER);
        voteVO.setVoterUserId(null);
        voteVO.setVoterUsername(null);
        voteVO.setVoterDisplayName(null);
    }

    private void desensitizeHistoryVoter(BattleHistoryVO row) {
        if (row == null) {
            return;
        }
        if (row.getVoterUserId() == null) {
            // 该场对战尚无投票人信息
            row.setVoter(null);
            row.setVoterUsername(null);
            row.setVoterDisplayName(null);
            return;
        }
        if (isAdmin()) {
            row.setVoter(preferHistoryVoterName(row));
            return;
        }
        Long currentUserId = UserContext.getUserId();
        if (currentUserId != null && Objects.equals(currentUserId, row.getVoterUserId())) {
            row.setVoter(preferHistoryVoterName(row));
            return;
        }
        row.setVoter(ANONYMOUS_VOTER);
        row.setVoterUserId(null);
        row.setVoterUsername(null);
        row.setVoterDisplayName(null);
    }

    private boolean isAdmin() {
        return "admin".equals(UserContext.getRole());
    }

    private String preferVoterName(BattleVoteVO vote) {
        if (vote == null) {
            return null;
        }
        return chooseName(vote.getVoterDisplayName(), vote.getVoterUsername());
    }

    private String preferHistoryVoterName(BattleHistoryVO row) {
        return chooseName(row.getVoterDisplayName(), row.getVoterUsername());
    }

    private String chooseName(String displayName, String username) {
        if (displayName != null && !displayName.isBlank()) {
            return displayName;
        }
        return username;
    }

}
