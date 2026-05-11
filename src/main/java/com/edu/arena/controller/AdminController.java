package com.edu.arena.controller;

import com.edu.arena.common.exception.BusinessException;
import com.edu.arena.common.result.Result;
import com.edu.arena.common.utils.UserContext;
import com.edu.arena.dto.request.AddModelRequest;
import com.edu.arena.dto.request.ExportQuery;
import com.edu.arena.dto.response.ModelProbeResultVO;
import com.edu.arena.entity.Model;
import com.edu.arena.service.ExportService;
import com.edu.arena.service.ModelService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

import java.io.IOException;
import java.io.OutputStream;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Admin Controller
 */
@Slf4j
@Tag(name = "Admin API")
@RestController
@RequestMapping("/api/admin")
@RequiredArgsConstructor
public class AdminController {

    private final ModelService modelService;
    private final ExportService exportService;

    @Value("${ai.api-key:}")
    private String apiKey;

    /**
     * Check admin permission
     */
    private void checkAdmin() {
        Long userId = UserContext.getUserId();
        if (userId == null) {
            throw new BusinessException(401, "Please login first");
        }
        if (!"admin".equals(UserContext.getRole())) {
            throw new BusinessException(403, "Admin permission required");
        }
    }

    @Operation(summary = "Get all models")
    @GetMapping("/models")
    public Result<List<Model>> getModels() {
        checkAdmin();
        List<Model> models = modelService.getAllModels();
        return Result.success(models);
    }

    @Operation(summary = "Add model")
    @PostMapping("/models")
    public Result<Void> addModel(@Valid @RequestBody AddModelRequest request) {
        checkAdmin();
        modelService.addModel(request);
        return Result.success("Model added", null);
    }

    @Operation(summary = "Toggle model status")
    @PostMapping("/models/{id}/toggle")
    public Result<Void> toggleModel(@PathVariable Long id) {
        checkAdmin();
        modelService.toggleModelStatus(id);
        return Result.success("Status updated", null);
    }

    @Operation(summary = "Probe all models with test images")
    @PostMapping("/models/probe")
    public Result<List<ModelProbeResultVO>> probeModels() {
        checkAdmin();
        return Result.success(modelService.probeAllModels());
    }

    @Operation(summary = "Get statistics")
    @GetMapping("/stats")
    public Result<Map<String, Object>> getStats() {
        checkAdmin();
        Map<String, Object> stats = new HashMap<>();
        stats.put("activeModels", modelService.getActiveModels().size());
        stats.put("total_battles", modelService.getTotalBattles());
        stats.put("total_users", modelService.getTotalUsers());
        return Result.success(stats);
    }

    @Operation(summary = "Get config")
    @GetMapping("/config")
    public Result<Map<String, Object>> getConfig() {
        checkAdmin();
        Map<String, Object> config = new HashMap<>();
        config.put("eloK", 32);
        config.put("eloInitial", 1500);
        config.put("api_configured", apiKey != null && !apiKey.isEmpty());
        return Result.success(config);
    }

    @Operation(summary = "Update config")
    @PostMapping("/config")
    public Result<Void> updateConfig(@RequestBody Map<String, Object> request) {
        checkAdmin();
        Integer eloK = (Integer) request.get("elo_k");
        if (eloK != null && eloK > 0) {
            log.info("ELO K值更新请求: eloK={}", eloK);
            // TODO: 持久化配置
        }
        return Result.success("配置已保存", null);
    }

    @Operation(summary = "Set API Key")
    @PostMapping("/set_api_key")
    public Result<Void> setApiKey(@RequestBody Map<String, String> request) {
        checkAdmin();
        String newKey = request.get("api_key");
        if (newKey == null || newKey.trim().isEmpty()) {
            throw new BusinessException(400, "API Key cannot be empty");
        }
        return Result.success("API Key saved (requires restart to take effect)", null);
    }

    @Operation(summary = "Get quality logs")
    @GetMapping("/quality_logs")
    public Result<List<Map<String, Object>>> getQualityLogs() {
        checkAdmin();
        return Result.success(List.of());
    }

    /**
     * 偏好数据集导出（唯一主接口）
     *
     * <p>固定输出 ZIP 包，内含 {@code data.jsonl}（每条 battle 完整数据）+
     * {@code images/task_{id}/*.jpg|png|webp}（作文图片，按 task 去重）+ {@code manifest.json}（导出元信息）。</p>
     *
     * <p><b>仅导出 status=voted 的对战</b>，脏数据（generating/ready/failed）一律过滤。</p>
     *
     * <p>查询参数（全部可选）：
     * <ul>
     *   <li>{@code winner}：A/B/tie 过滤</li>
     *   <li>{@code modelId}：限定参与方，可传数据库主键 ID 或 model_id 字符串</li>
     *   <li>{@code startDate} / {@code endDate}：按 created_at 闭区间，格式 yyyy-MM-dd</li>
     *   <li>{@code battleId}：精确导出某条</li>
     *   <li>{@code includeImages}：默认 true，是否在 ZIP 内打包 images/</li>
     *   <li>{@code limit}：最多导出条数</li>
     * </ul>
     */
    @Operation(summary = "Export preference dataset (ZIP, jsonl + images)")
    @GetMapping("/export/dataset.zip")
    public ResponseEntity<StreamingResponseBody> exportDatasetZip(ExportQuery query, HttpServletResponse response) {
        checkAdmin();
        long startMs = System.currentTimeMillis();
        log.info("[导出] 收到请求 userId={} query={}", UserContext.getUserId(), query);
        String filename = "preference_export_"
                + LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss"))
                + ".zip";

        StreamingResponseBody body = (OutputStream out) -> {
            try {
                log.info("[导出] 开始流式写出 filename={}", filename);
                exportService.exportZip(query, out);
                log.info("[导出] 完成 filename={} 耗时={}ms", filename, System.currentTimeMillis() - startMs);
            } catch (IOException e) {
                log.error("[导出] ZIP 失败 filename={} 耗时={}ms", filename, System.currentTimeMillis() - startMs, e);
                throw e;
            }
        };

        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=" + filename)
                .header(HttpHeaders.CACHE_CONTROL, "no-store")
                .contentType(MediaType.parseMediaType("application/zip"))
                .body(body);
    }
}
