package com.edu.arena.dto.request;

import lombok.Data;

/**
 * 多模态消息内容项
 * 用于构建支持文本+图片的消息内容
 */
@Data
public class MessageContentItem {

    /**
     * 内容类型: text, image_url
     */
    private String type;

    /**
     * 文本内容(type=text时使用)
     */
    private String text;

    /**
     * 图片URL信息(type=image_url时使用)
     */
    private ImageUrl image_url;

    /**
     * 创建文本内容项
     */
    public static MessageContentItem textItem(String text) {
        MessageContentItem item = new MessageContentItem();
        item.setType("text");
        item.setText(text);
        return item;
    }

    /**
     * 从纯Base64创建图片内容项
     * @param base64Data 纯Base64数据(不含data:image前缀)
     * @param mimeType 图片类型: image/png, image/jpeg, image/webp
     */
    public static MessageContentItem fromBase64(String base64Data, String mimeType) {
        MessageContentItem item = new MessageContentItem();
        item.setType("image_url");
        item.setImage_url(new ImageUrl("data:" + mimeType + ";base64," + base64Data));
        return item;
    }

    /**
     * 从完整Data URL创建图片内容项
     * @param dataUrl 完整的Data URL格式
     */
    public static MessageContentItem fromDataUrl(String dataUrl) {
        MessageContentItem item = new MessageContentItem();
        item.setType("image_url");
        item.setImage_url(new ImageUrl(dataUrl));
        return item;
    }

    /**
     * 图片URL信息
     */
    @Data
    public static class ImageUrl {
        /**
         * 图片URL或Base64数据URI
         */
        private String url;

        /**
         * 清晰度: low, high, auto (可选)
         */
        private String detail = "auto";

        public ImageUrl() {}

        public ImageUrl(String url) {
            this.url = url;
        }
    }

}
