package com.edu.arena.aiclient;

import com.edu.arena.common.cache.CacheService;
import com.edu.arena.dto.request.MessageContentItem;
import com.edu.arena.dto.response.ModelInfoVO;
import com.edu.arena.entity.Task;
import lombok.extern.slf4j.Slf4j;
import okhttp3.*;
import okhttp3.sse.EventSource;
import okhttp3.sse.EventSourceListener;
import okhttp3.sse.EventSources;
import org.jetbrains.annotations.NotNull;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Base64;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.function.Consumer;

import cn.hutool.core.lang.TypeReference;

/**
 * AI模型客户端
 */
@Slf4j
@Component
public class AiClient {

    @Value("${ai.api-key:}")
    private String apiKey;

    @Value("${ai.base-url:https://api.aihubmix.com/v1/chat/completions}")
    private String baseUrl;

    @Value("${ai.max-tokens:2048}")
    private Integer maxTokens;

    /**
     * 模型信息API地址
     */
    private static final String MODELS_API_URL = "https://aihubmix.com/api/v1/models";

    private final OkHttpClient httpClient;      // SSE 流式专用
    private final OkHttpClient syncHttpClient;   // 同步请求专用
    
    // 使用 setter 注入避免循环依赖
    private CacheService cacheService;
    
    @org.springframework.beans.factory.annotation.Autowired
    public void setCacheService(CacheService cacheService) {
        this.cacheService = cacheService;
    }

    public AiClient() {
        // SSE 流式专用 HTTP 客户端
        // 支持多个并行 SSE 连接，每个连接独立
        // 配置 Dispatcher 以支持并行 SSE 请求
        okhttp3.Dispatcher dispatcher = new okhttp3.Dispatcher();
        dispatcher.setMaxRequests(64);           // 全局最大并发请求数
        dispatcher.setMaxRequestsPerHost(10);    // 同一主机最大并发请求数（支持多模型并行）
        
        this.httpClient = new OkHttpClient.Builder()
                .connectTimeout(60, TimeUnit.SECONDS)
                .readTimeout(0, TimeUnit.SECONDS)  // SSE 无读取超时
                .writeTimeout(60, TimeUnit.SECONDS)
                .retryOnConnectionFailure(true)
                // 使用连接池支持并行连接（最多10个空闲连接）
                .connectionPool(new ConnectionPool(10, 5, TimeUnit.MINUTES))
                // 强制使用 HTTP/1.1 (SSE 与 HTTP/2 兼容性问题)
                .protocols(List.of(Protocol.HTTP_1_1))
                // 设置 Dispatcher 支持并行请求
                .dispatcher(dispatcher)
                .build();
        
        // 同步请求使用标准配置
        this.syncHttpClient = new OkHttpClient.Builder()
                .connectTimeout(30, TimeUnit.SECONDS)
                .readTimeout(60, TimeUnit.SECONDS)
                .writeTimeout(30, TimeUnit.SECONDS)
                .connectionPool(new ConnectionPool(5, 5, TimeUnit.MINUTES))
                .build();
    }

    /**
     * 检查API是否已配置
     */
    public boolean isConfigured() {
        return apiKey != null && !apiKey.isEmpty();
    }

    /**
     * 从平台获取模型信息（带缓存）
     * @param modelId 模型ID，如 "gpt-5.4"
     * @return 模型信息，如果未找到返回null
     */
    @SuppressWarnings("unchecked")
    public ModelInfoVO fetchModelInfo(String modelId) {
        // 尝试从缓存获取
        if (cacheService != null) {
            ModelInfoVO cached = cacheService.getOrLoad(
                    cacheService.getApiModelInfoKey(modelId),
                    CacheService.TTL_API,
                    () -> fetchModelInfoFromApi(modelId)
            );
            return cached;
        }
        // 缓存服务不可用时直接调用 API
        return fetchModelInfoFromApi(modelId);
    }

    public Task buildProbeTask(List<String> imageBase64List) {
        Task task = new Task();
        task.setEssayTitle("图片识别与作文批改能力探测");
        task.setEssayContent("");
        task.setRequirements("这是模型可用性测试。请识别图片中的手写作文内容，并用2-3句话简要评价。无需展开详细批改。");
        task.setHasImages(imageBase64List != null && !imageBase64List.isEmpty());
        task.setImageCount(imageBase64List == null ? 0 : imageBase64List.size());
        task.setImageBase64List(imageBase64List);
        return task;
    }

    public String imageFileToBase64(byte[] bytes) {
        return Base64.getEncoder().encodeToString(bytes);
    }

    private String buildRequestSummary(String modelId, Task task) {
        boolean hasImages = task.getImageBase64List() != null && !task.getImageBase64List().isEmpty();
        int essayLength = task.getEssayContent() == null ? 0 : task.getEssayContent().length();
        int titleLength = task.getEssayTitle() == null ? 0 : task.getEssayTitle().length();
        int imageCount = hasImages ? task.getImageBase64List().size() : 0;
        List<Integer> imageSizes = new ArrayList<>();
        if (hasImages) {
            for (String image : task.getImageBase64List()) {
                imageSizes.add(image == null ? 0 : image.length());
            }
        }
        return String.format("modelId=%s, hasImages=%s, imageCount=%d, imageSizes=%s, titleLength=%d, essayLength=%d",
                modelId, hasImages, imageCount, imageSizes, titleLength, essayLength);
    }

    private String sanitizeLogSnippet(String raw) {
        if (raw == null || raw.isEmpty()) {
            return "";
        }
        String sanitized = raw.replaceAll("data:image/[^;]+;base64,[A-Za-z0-9+/=]+", "[BASE64_IMAGE]")
                .replaceAll("[A-Za-z0-9+/=]{200,}", "[BASE64_BLOCK]");
        return sanitized.length() > 200 ? sanitized.substring(0, 200) + "..." : sanitized;
    }

    /**
     * 从API获取模型信息（实际调用）
     */
    @SuppressWarnings("unchecked")
    private ModelInfoVO fetchModelInfoFromApi(String modelId) {
        try {
            String url = MODELS_API_URL + "?model=" + modelId;
            
            Request.Builder requestBuilder = new Request.Builder()
                    .url(url)
                    .header("Content-Type", "application/json")
                    .get();
            
            // 获取模型列表API不需要认证，但如果有API Key也可以添加
            if (apiKey != null && !apiKey.isEmpty()) {
                requestBuilder.header("Authorization", "Bearer " + apiKey);
            }
            
            Request request = requestBuilder.build();

            try (Response response = syncHttpClient.newCall(request).execute()) {
                if (!response.isSuccessful()) {
                    log.error("获取模型信息失败: modelId={}, httpCode={}", modelId, response.code());
                    return null;
                }

                String responseBody = response.body().string();
                log.debug("模型信息API响应摘要: modelId={}, bodyLength={}", modelId, responseBody.length());
                
                Map<String, Object> json = cn.hutool.json.JSONUtil.toBean(responseBody, new TypeReference<Map<String, Object>>() {}, false);
                
                Boolean success = (Boolean) json.get("success");
                if (success == null || !success) {
                    log.error("模型信息API返回失败: modelId={}, success={}", modelId, success);
                    return null;
                }

                List<Map<String, Object>> dataList = (List<Map<String, Object>>) json.get("data");
                if (dataList == null || dataList.isEmpty()) {
                    log.warn("未找到模型: {}, API返回data为空或null", modelId);
                    return null;
                }

                // 取第一个匹配的模型
                Map<String, Object> data = dataList.get(0);
                
                ModelInfoVO vo = new ModelInfoVO();
                vo.setModelId((String) data.get("model_id"));
                // API返回的是model_id，没有model_name字段，用model_id作为名称
                String modelName = (String) data.get("model_name");
                if (modelName == null || modelName.isEmpty()) {
                    modelName = (String) data.get("model_id");
                }
                vo.setModelName(modelName);
                vo.setDesc((String) data.get("desc"));
                vo.setTypes((String) data.get("types"));
                vo.setFeatures((String) data.get("features"));
                vo.setInputModalities((String) data.get("input_modalities"));
                
                // 处理整数类型
                Object contextLength = data.get("context_length");
                if (contextLength != null) {
                    vo.setContextLength(((Number) contextLength).intValue());
                }
                
                Object maxOutput = data.get("max_output");
                if (maxOutput != null) {
                    vo.setMaxOutput(((Number) maxOutput).intValue());
                }

                // 处理价格
                Map<String, Object> pricing = (Map<String, Object>) data.get("pricing");
                if (pricing != null) {
                    ModelInfoVO.Pricing p = new ModelInfoVO.Pricing();
                    if (pricing.get("input") != null) {
                        p.setInput(new BigDecimal(pricing.get("input").toString()));
                    }
                    if (pricing.get("output") != null) {
                        p.setOutput(new BigDecimal(pricing.get("output").toString()));
                    }
                    vo.setPricing(p);
                }

                log.info("成功获取模型信息: modelId={}, modelName={}", modelId, vo.getModelName());
                return vo;
            }
        } catch (Exception e) {
            log.error("获取模型信息异常: modelId={}, message={}", modelId, e.getMessage(), e);
            return null;
        }
    }

    /**
     * 验证模型是否支持 chat/completions 接口
     * @param modelId 模型ID
     * @return 验证结果：支持返回true，不支持返回false，无法验证返回null
     */
    public Boolean validateChatModel(String modelId) {
        ModelInfoVO info = fetchModelInfo(modelId);
        if (info == null) {
            log.warn("无法获取模型信息: {}", modelId);
            return null; // 无法验证
        }
        
        String types = info.getTypes();
        if (types == null || types.isEmpty()) {
            log.warn("模型 {} 没有 types 信息", modelId);
            return null; // 无法验证
        }
        
        // types 格式通常是 "chat,text" 或 "chat" 等
        boolean supportsChat = types.toLowerCase().contains("chat");
        log.info("模型 {} types={}, 支持chat={}", modelId, types, supportsChat);
        return supportsChat;
    }

    /**
     * 构建批改Prompt(纯文本版本 - 备用，图片模式下使用buildMessageContent)
     * 优化版：增强角色定义、细化评分标准、引导思维链、适配无正文场景
     */
    public String buildPrompt(Task task) {
        StringBuilder prompt = new StringBuilder();
        
        // 1. 角色定义 - 更具体的专业背景
        prompt.append("你是北京市中考语文阅卷组专家成员，拥有15年中学作文批改经验。\n");
        prompt.append("你熟悉中考作文评分标准，擅长发现学生作文的亮点与不足，并能给出有针对性的修改建议。\n");
        prompt.append("批改风格：客观公正、细致耐心、鼓励为主、建议具体。\n\n");
        
        // 2. 作文题目
        prompt.append("【作文题目】\n").append(task.getEssayTitle()).append("\n\n");
        
        // 3. 学生作文（适配无正文场景）
        if (task.getEssayContent() != null && !task.getEssayContent().isEmpty()) {
            prompt.append("【学生作文】\n").append(task.getEssayContent()).append("\n\n");
        } else {
            prompt.append("【说明】学生作文以图片形式提供，请结合图片内容进行批改。\n\n");
        }
        
        // 4. 批改要求（如有）
        if (task.getRequirements() != null && !task.getRequirements().isEmpty()) {
            prompt.append("【特别要求】\n").append(task.getRequirements()).append("\n\n");
        }
        
        // 5. 评分标准 - 细化每个档次的描述
        prompt.append("【评分标准】（总分40分）\n\n");
        prompt.append("一、主旨（9分）- 立意与内容\n");
        prompt.append("  8-9分：立意深刻，中心突出，内容充实，情感真挚\n");
        prompt.append("  5-7分：立意正确，中心明确，内容较充实\n");
        prompt.append("  3-4分：立意基本正确，中心不够明确，内容单薄\n");
        prompt.append("  0-2分：偏离题意，中心不明，内容空洞\n\n");
        
        prompt.append("二、想象（9分）- 创意与构思\n");
        prompt.append("  8-9分：想象丰富新颖，构思巧妙，有独特视角\n");
        prompt.append("  5-7分：想象较丰富，构思合理，有一定新意\n");
        prompt.append("  3-4分：想象一般，构思较平淡\n");
        prompt.append("  0-2分：缺乏想象，构思陈旧或混乱\n\n");
        
        prompt.append("三、逻辑（9分）- 结构与条理\n");
        prompt.append("  8-9分：结构严谨，层次分明，过渡自然，首尾呼应\n");
        prompt.append("  5-7分：结构完整，层次较清晰，过渡较自然\n");
        prompt.append("  3-4分：结构基本完整，层次不够清晰\n");
        prompt.append("  0-2分：结构混乱，层次不清\n\n");
        
        prompt.append("四、语言（9分）- 表达与文采\n");
        prompt.append("  8-9分：语言流畅优美，表达生动，几乎无病句\n");
        prompt.append("  5-7分：语言通顺，表达较清楚，偶有病句\n");
        prompt.append("  3-4分：语言基本通顺，有一些病句\n");
        prompt.append("  0-2分：语言不通顺，病句较多\n\n");
        
        prompt.append("五、书写（4分）- 规范与卷面\n");
        prompt.append("  4分：书写工整美观，标点规范，无错别字\n");
        prompt.append("  3分：书写较工整，标点基本规范，偶有错别字\n");
        prompt.append("  1-2分：书写潦草，标点不规范，错别字较多\n\n");
        
        // 6. 思维链引导
        prompt.append("【批改步骤】\n");
        prompt.append("第一步：通读全文，把握文章主旨和整体结构。\n");
        prompt.append("第二步：逐项对照评分标准，分析每个维度的表现。\n");
        prompt.append("第三步：给出各维度分数，总分写在最后。\n");
        prompt.append("第四步：总结优点、指出不足、提出建议。\n\n");
        
        // 7. 输出格式 - 更严格
        prompt.append("【输出格式】（必须严格按此格式，不要添加额外内容）\n");
        prompt.append("【主旨：X分】简要理由\n");
        prompt.append("【想象：X分】简要理由\n");
        prompt.append("【逻辑：X分】简要理由\n");
        prompt.append("【语言：X分】简要理由\n");
        prompt.append("【书写：X分】简要理由\n");
        prompt.append("【总分：X/40分】\n\n");
        prompt.append("【总体评价】\n60-100字的整体评语，概括文章的主要特点。\n\n");
        prompt.append("【优点】\n1. 具体优点一\n2. 具体优点二\n3. 具体优点三（可选）\n\n");
        prompt.append("【不足】\n1. 具体不足一\n2. 具体不足二（可选）\n\n");
        prompt.append("【建议】\n给出1-2条具体、可操作的修改建议，帮助学生提升。\n");
        
        return prompt.toString();
    }

    /**
     * 检测Base64图片的MIME类型
     * @param base64Data 纯Base64数据(不含data:image前缀)
     * @return MIME类型
     */
    private String detectMimeType(String base64Data) {
        // 根据Base64头部特征判断图片类型
        if (base64Data.startsWith("/9j/")) {
            return "image/jpeg";
        } else if (base64Data.startsWith("iVBORw0KGgo")) {
            return "image/png";
        } else if (base64Data.startsWith("UklGR")) {
            return "image/webp";
        } else if (base64Data.startsWith("R0lGOD")) {
            return "image/gif";
        }
        // 默认使用PNG
        return "image/png";
    }

    /**
     * 构建多模态消息内容(支持文本+图片)
     * 优化版：强化图片识别指引（手写体识别、段落分割），适配图片为主的输入模式
     * @param task 任务
     * @return 消息内容列表，包含文本和图片
     */
    public List<MessageContentItem> buildMessageContent(Task task) {
        List<MessageContentItem> content = new ArrayList<>();
        
        // 构建文本部分
        StringBuilder textPrompt = new StringBuilder();
        
        // 1. 角色定义
        textPrompt.append("你是北京市中考语文和英语阅卷组专家成员，拥有15年初三作文批改经验。\n");
        textPrompt.append("你熟悉中考作文评分标准，擅长发现学生作文的亮点与不足，并能给出有针对性的修改建议。\n");
        textPrompt.append("批改风格：客观公正、细致耐心、鼓励为主、建议具体。\n\n");
        
        // 2. 作文题目
        textPrompt.append("【作文题目】\n").append(task.getEssayTitle()).append("\n\n");
        
        // 3. 图片识别指引（强化版）
        boolean hasImages = task.getImageBase64List() != null && !task.getImageBase64List().isEmpty();
        if (hasImages) {
            textPrompt.append("【学生作文图片】\n");
            textPrompt.append("以下是学生手写作文的").append(task.getImageBase64List().size()).append("张图片。\n");
            textPrompt.append("请按以下步骤处理图片：\n");
            textPrompt.append("1. 仔细辨认图片中的手写文字内容，注意区分易混淆字（如：已/己、末/未、撤/撒等）\n");
            textPrompt.append("2. 按图片顺序拼接完整作文内容，注意段落分割和上下文衔接\n");
            textPrompt.append("3. 关注书写工整度、字迹清晰度、涂改情况等书写维度信息\n");
            textPrompt.append("4. 如果图片模糊或部分文字无法辨认，请标注并基于可辨认内容进行评价\n\n");
        }
        
        // 4. 如果有文本内容
        if (task.getEssayContent() != null && !task.getEssayContent().isEmpty()) {
            textPrompt.append("【学生作文文字内容】\n").append(task.getEssayContent()).append("\n\n");
        }
        
        // 5. 批改要求（如有）
        if (task.getRequirements() != null && !task.getRequirements().isEmpty()) {
            textPrompt.append("【特别要求】\n").append(task.getRequirements()).append("\n\n");
        }
        
        // 6. 评分标准
        textPrompt.append("【评分标准】（总分40分）\n\n");
        textPrompt.append("一、主旨（9分）- 立意与内容\n");
        textPrompt.append("  8-9分：立意深刻，中心突出，内容充实，情感真挚\n");
        textPrompt.append("  5-7分：立意正确，中心明确，内容较充实\n");
        textPrompt.append("  3-4分：立意基本正确，中心不够明确，内容单薄\n");
        textPrompt.append("  0-2分：偏离题意，中心不明，内容空洞\n\n");
        
        textPrompt.append("二、想象（9分）- 创意与构思\n");
        textPrompt.append("  8-9分：想象丰富新颖，构思巧妙，有独特视角\n");
        textPrompt.append("  5-7分：想象较丰富，构思合理，有一定新意\n");
        textPrompt.append("  3-4分：想象一般，构思较平淡\n");
        textPrompt.append("  0-2分：缺乏想象，构思陈旧或混乱\n\n");
        
        textPrompt.append("三、逻辑（9分）- 结构与条理\n");
        textPrompt.append("  8-9分：结构严谨，层次分明，过渡自然，首尾呼应\n");
        textPrompt.append("  5-7分：结构完整，层次较清晰，过渡较自然\n");
        textPrompt.append("  3-4分：结构基本完整，层次不够清晰\n");
        textPrompt.append("  0-2分：结构混乱，层次不清\n\n");
        
        textPrompt.append("四、语言（9分）- 表达与文采\n");
        textPrompt.append("  8-9分：语言流畅优美，表达生动，几乎无病句\n");
        textPrompt.append("  5-7分：语言通顺，表达较清楚，偶有病句\n");
        textPrompt.append("  3-4分：语言基本通顺，有一些病句\n");
        textPrompt.append("  0-2分：语言不通顺，病句较多\n\n");
        
        textPrompt.append("五、书写（4分）- 规范与卷面\n");
        textPrompt.append("  4分：书写工整美观，标点规范，无错别字\n");
        textPrompt.append("  3分：书写较工整，标点基本规范，偶有错别字\n");
        textPrompt.append("  1-2分：书写潦草，标点不规范，错别字较多\n\n");
        
        // 7. 思维链引导
        textPrompt.append("【批改步骤】\n");
        textPrompt.append("第一步：仔细阅读图片或文字内容，把握文章主旨和整体结构。\n");
        textPrompt.append("第二步：逐项对照评分标准，分析每个维度的表现。\n");
        textPrompt.append("第三步：给出各维度分数，总分写在最后。\n");
        textPrompt.append("第四步：总结优点、指出不足、提出建议。\n\n");
        
        // 8. 输出格式
        textPrompt.append("【输出格式】（必须严格按此格式，不要添加额外内容）\n");
        textPrompt.append("【主旨：X分】简要理由\n");
        textPrompt.append("【想象：X分】简要理由\n");
        textPrompt.append("【逻辑：X分】简要理由\n");
        textPrompt.append("【语言：X分】简要理由\n");
        textPrompt.append("【书写：X分】简要理由\n");
        textPrompt.append("【总分：X/40分】\n\n");
        textPrompt.append("【总体评价】\n60-100字的整体评语，概括文章的主要特点。\n\n");
        textPrompt.append("【优点】\n1. 具体优点一\n2. 具体优点二\n3. 具体优点三（可选）\n\n");
        textPrompt.append("【不足】\n1. 具体不足一\n2. 具体不足二（可选）\n\n");
        textPrompt.append("【建议】\n给出1-2条具体、可操作的修改建议，帮助学生提升。\n");
        
        // 添加文本内容项
        content.add(MessageContentItem.textItem(textPrompt.toString()));
        
        // 添加图片内容项
        if (hasImages) {
            for (String base64Data : task.getImageBase64List()) {
                String mimeType = detectMimeType(base64Data);
                content.add(MessageContentItem.fromBase64(base64Data, mimeType));
            }
        }
        
        return content;
    }

    /**
     * 流式生成(支持多模态)
     * 使用独立的 OkHttpClient 实例确保真正的并行请求
     */
    @SuppressWarnings("unchecked")
    public void streamGenerate(String modelId, Task task, Consumer<String> onChunk, Runnable onComplete, Consumer<Exception> onError) {
        if (!isConfigured()) {
            onError.accept(new IllegalStateException("API Key未配置"));
            return;
        }

        log.info("开始流式生成请求: {}", buildRequestSummary(modelId, task));

        // 判断是否需要多模态
        boolean hasImages = task.getImageBase64List() != null && !task.getImageBase64List().isEmpty();
        
        Map<String, Object> body = new HashMap<>();
        body.put("model", modelId);
        
        if (hasImages) {
            // 多模态消息：content为数组
            List<MessageContentItem> content = buildMessageContent(task);
            body.put("messages", List.of(Map.of("role", "user", "content", content)));
            log.debug("使用多模态请求摘要: modelId={}, imageCount={}", modelId, task.getImageBase64List().size());
        } else {
            // 纯文本消息：content为字符串
            String prompt = buildPrompt(task);
            body.put("messages", List.of(Map.of("role", "user", "content", prompt)));
        }
        
        body.put("stream", true);
        // temperature 和 max_tokens 都是可选参数，不设置让 API 使用默认值，兼容所有模型

        String jsonBody = cn.hutool.json.JSONUtil.toJsonStr(body);

        Request request = new Request.Builder()
                .url(baseUrl)
                .header("Authorization", "Bearer " + apiKey)
                .header("Content-Type", "application/json")
                .header("Accept", "text/event-stream")
                .post(RequestBody.create(jsonBody, MediaType.parse("application/json")))
                .build();

        // 为每个请求创建独立的 EventSource.Factory，确保并行请求不会互相阻塞
        // 使用 httpClient（已配置连接池支持多连接）
        EventSource.Factory factory = EventSources.createFactory(httpClient);
        
        factory.newEventSource(request, new EventSourceListener() {
            private final StringBuilder content = new StringBuilder();
            private boolean completed = false;

            @Override
            public void onOpen(@NotNull EventSource eventSource, @NotNull Response response) {
                log.debug("SSE connection opened for model: {}", modelId);
            }

            @Override
            public void onEvent(@NotNull EventSource eventSource, String id, String type, String data) {
                if (completed) return;
                
                if ("[DONE]".equals(data)) {
                    completed = true;
                    log.info("SSE stream completed for model: {}, content length: {}", modelId, content.length());
                    onComplete.run();
                    return;
                }

                try {
                    Map<String, Object> json = cn.hutool.json.JSONUtil.toBean(data, new TypeReference<Map<String, Object>>() {}, false);
                    List<Map<String, Object>> choices = (List<Map<String, Object>>) json.get("choices");
                    if (choices != null && !choices.isEmpty()) {
                        Map<String, Object> delta = (Map<String, Object>) choices.get(0).get("delta");
                        if (delta != null) {
                            String text = (String) delta.get("content");
                            if (text != null) {
                                content.append(text);
                                onChunk.accept(text);
                            }
                        }
                    }
                } catch (Exception e) {
                    log.debug("Parse SSE data error: modelId={}, message={}", modelId, e.getMessage());
                }
            }

            @Override
            public void onClosed(@NotNull EventSource eventSource) {
                log.debug("SSE connection closed for model: {}", modelId);
                if (!completed) {
                    completed = true;
                    onComplete.run();
                }
            }

            @Override
            public void onFailure(@NotNull EventSource eventSource, Throwable t, Response response) {
                if (completed) return;
                completed = true;
                onError.accept(new Exception(buildErrorMessage(modelId, response, t)));
            }
        });
    }

    /**
     * 同步生成(支持多模态)
     */
    @SuppressWarnings("unchecked")
    public String generate(String modelId, Task task) throws IOException {
        if (!isConfigured()) {
            throw new IOException("API Key未配置");
        }

        log.info("开始同步生成请求: {}", buildRequestSummary(modelId, task));
        boolean hasImages = task.getImageBase64List() != null && !task.getImageBase64List().isEmpty();
        
        Map<String, Object> body = new HashMap<>();
        body.put("model", modelId);
        
        if (hasImages) {
            // 多模态消息：content为数组
            List<MessageContentItem> content = buildMessageContent(task);
            body.put("messages", List.of(Map.of("role", "user", "content", content)));
        } else {
            // 纯文本消息：content为字符串
            String prompt = buildPrompt(task);
            body.put("messages", List.of(Map.of("role", "user", "content", prompt)));
        }
        
        // temperature 和 max_tokens 都是可选参数，不设置让 API 使用默认值，兼容所有模型

        String jsonBody = cn.hutool.json.JSONUtil.toJsonStr(body);

        Request request = new Request.Builder()
                .url(baseUrl)
                .header("Authorization", "Bearer " + apiKey)
                .header("Content-Type", "application/json")
                .post(RequestBody.create(jsonBody, MediaType.parse("application/json")))
                .build();

        try (Response response = syncHttpClient.newCall(request).execute()) {
            if (!response.isSuccessful()) {
                throw new IOException(buildErrorMessage(modelId, response, null));
            }

            String responseBody = response.body().string();
            Map<String, Object> json = cn.hutool.json.JSONUtil.toBean(responseBody, new TypeReference<Map<String, Object>>() {}, false);
            List<Map<String, Object>> choices = (List<Map<String, Object>>) json.get("choices");
            if (choices != null && !choices.isEmpty()) {
                Map<String, Object> message = (Map<String, Object>) choices.get(0).get("message");
                if (message != null) {
                    String content = (String) message.get("content");
                    if (content != null && !content.isBlank()) {
                        return content;
                    }
                }
            }
            throw new IOException("模型未返回有效内容");
        }
    }

    private String buildErrorMessage(String modelId, Response response, Throwable throwable) {
        if (response != null) {
            int code = response.code();
            String body = "";
            try {
                body = response.body() != null ? response.body().string() : "";
            } catch (Exception ignored) {
            }

            String errorMsg;
            if (code == 404 && body.contains("not a chat model")) {
                errorMsg = "模型 " + modelId + " 不支持对话接口";
            } else if (code == 401) {
                errorMsg = "API Key 无效或已过期";
            } else if (code == 429) {
                errorMsg = "API 调用频率超限";
            } else if (code == 500 || code == 502 || code == 503) {
                errorMsg = "API 服务暂时不可用";
            } else {
                errorMsg = "HTTP " + code;
            }
            log.error("模型调用失败: modelId={}, code={}, bodySnippet={}", modelId, code, sanitizeLogSnippet(body));
            return errorMsg;
        }

        String errorMsg = throwable != null ? throwable.getMessage() : "Unknown error";
        log.error("模型调用异常: modelId={}, message={}", modelId, sanitizeLogSnippet(errorMsg));
        return errorMsg;
    }

}
