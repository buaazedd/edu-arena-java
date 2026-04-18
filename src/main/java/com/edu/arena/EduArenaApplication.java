package com.edu.arena;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;

/**
 * AI模型作文批改对战评测平台启动类
 */
@SpringBootApplication
@MapperScan("com.edu.arena.mapper")
@EnableAsync
public class EduArenaApplication {

    public static void main(String[] args) {
        SpringApplication.run(EduArenaApplication.class, args);
    }

}
