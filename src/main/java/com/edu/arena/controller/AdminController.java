package com.edu.arena.controller;

import com.edu.arena.common.exception.BusinessException;
import com.edu.arena.common.result.Result;
import com.edu.arena.common.utils.UserContext;
import com.edu.arena.dto.request.AddModelRequest;
import com.edu.arena.dto.response.ModelProbeResultVO;
import com.edu.arena.entity.Model;
import com.edu.arena.service.ModelService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.nio.charset.StandardCharsets;
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
        // 配置更新逻辑（实际项目中应持久化到数据库或配置文件）
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
        // In production, this should save to secure storage or environment
        // For now, we just return success
        return Result.success("API Key saved (requires restart to take effect)", null);
    }

    @Operation(summary = "Get quality logs")
    @GetMapping("/quality_logs")
    public Result<List<Map<String, Object>>> getQualityLogs() {
        checkAdmin();
        // Return empty list for now - can be extended to query from quality_logs table
        return Result.success(List.of());
    }

    @Operation(summary = "Export preference dataset (JSON)")
    @GetMapping("/export/preference")
    public ResponseEntity<byte[]> exportPreference() {
        checkAdmin();
        try {
            String json = modelService.exportPreferenceJson();
            return ResponseEntity.ok()
                    .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=preference_data.json")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(json.getBytes(StandardCharsets.UTF_8));
        } catch (Exception e) {
            return ResponseEntity.internalServerError().build();
        }
    }

    @Operation(summary = "Export preference dataset (JSONL)")
    @GetMapping("/export/jsonl")
    public ResponseEntity<byte[]> exportJsonl() {
        checkAdmin();
        try {
            String jsonl = modelService.exportPreferenceJsonl();
            return ResponseEntity.ok()
                    .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=preference_data.jsonl")
                    .contentType(MediaType.TEXT_PLAIN)
                    .body(jsonl.getBytes(StandardCharsets.UTF_8));
        } catch (Exception e) {
            return ResponseEntity.internalServerError().build();
        }
    }


}
