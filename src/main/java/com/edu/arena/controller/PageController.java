package com.edu.arena.controller;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

/**
 * Page Controller - Handles frontend page routing
 */
@Controller
public class PageController {

    @GetMapping("/")
    public String index() {
        return "index";
    }

    @GetMapping("/battle")
    public String battle() {
        return "battle";
    }

    @GetMapping("/leaderboard")
    public String leaderboard() {
        return "leaderboard";
    }

    @GetMapping("/history")
    public String history() {
        return "history";
    }

    @GetMapping("/admin")
    public String admin() {
        return "admin";
    }

}
