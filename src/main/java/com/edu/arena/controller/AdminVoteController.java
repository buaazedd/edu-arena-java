package com.edu.arena.controller;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.edu.arena.common.exception.BusinessException;
import com.edu.arena.common.result.Result;
import com.edu.arena.common.utils.UserContext;
import com.edu.arena.dto.request.AdminVoteQuery;
import com.edu.arena.dto.response.AdminVoteItemVO;
import com.edu.arena.service.VoteQueryService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 管理员投票记录接口（仅 admin 可访问）。
 */
@Slf4j
@Tag(name = "Admin Vote API")
@RestController
@RequestMapping("/api/admin")
@RequiredArgsConstructor
public class AdminVoteController {

    private final VoteQueryService voteQueryService;

    private void checkAdmin() {
        Long userId = UserContext.getUserId();
        if (userId == null) {
            throw new BusinessException(401, "Please login first");
        }
        if (!"admin".equals(UserContext.getRole())) {
            throw new BusinessException(403, "Admin permission required");
        }
    }

    @Operation(summary = "后台投票记录分页查询（admin）")
    @GetMapping("/votes")
    public Result<IPage<AdminVoteItemVO>> listVotes(@ModelAttribute AdminVoteQuery query) {
        checkAdmin();
        IPage<AdminVoteItemVO> pageResult = voteQueryService.pageVotes(query);
        log.info("admin={} 查询投票记录: page={}, size={}, userId={}, battleId={}, keyword={}, start={}, end={}, total={}",
                UserContext.getUserId(), query.getPage(), query.getSize(),
                query.getUserId(), query.getBattleId(), query.getKeyword(),
                query.getStartDate(), query.getEndDate(), pageResult.getTotal());
        return Result.success(pageResult);
    }
}
