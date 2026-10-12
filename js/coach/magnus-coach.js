/*
 * ChessMate Magnus Coach Animation Controller
 *
 * Analysis remains completely separate from presentation.
 * Coach Core / API decides what happened.
 * This controller decides how Magnus reacts visually.
 */

const MAGNUS_STATES = Object.freeze({
    brilliant: {
        image: "brilliant.png",
        mood: "confident",
        reaction: "celebrate"
    },

    great: {
        image: "great.png",
        mood: "impressed",
        reaction: "nod"
    },

    best: {
        image: "best.png",
        mood: "approving",
        reaction: "nod"
    },

    good: {
        image: "good.png",
        mood: "satisfied",
        reaction: "nod"
    },

    book: {
        image: "book.png",
        mood: "analytical",
        reaction: "think"
    },

    thinking: {
        image: "thinking.png",
        mood: "thinking",
        reaction: "think"
    },

    inaccuracy: {
        image: "inaccuracy.png",
        mood: "skeptical",
        reaction: "question"
    },

    mistake: {
        image: "mistake.png",
        mood: "disappointed",
        reaction: "disappointed"
    },

    blunder: {
        image: "blunder.png",
        mood: "shocked",
        reaction: "shock"
    },

    checkmate: {
        image: "checkmate.png",
        mood: "celebratory",
        reaction: "celebrate"
    }
});

function magnusNormalizeState(value) {
    if (!value) return "thinking";

    const state = String(value)
        .toLowerCase()
        .trim();

    if (MAGNUS_STATES[state]) {
        return state;
    }

    if (
        state === "tactical" ||
        state === "tactical_miss" ||
        state === "missed_tactic"
    ) {
        return "thinking";
    }

    return "thinking";
}

function magnusStateFromCoach(coach) {
    if (!coach) return "thinking";

    const label =
        coach?.classification?.label ||
        coach?.classification?.name ||
        coach?.label ||
        coach?.classification;

    const normalized = magnusNormalizeState(label);

    /*
     * Preserve actual move classification first.
     */
    if (MAGNUS_STATES[normalized]) {
        return normalized;
    }

    /*
     * If there is no usable classification but the Coach
     * has identified tactical reasoning, Magnus thinks.
     */
    if (
        coach?.reasoning?.tactical_effect ||
        coach?.explanation?.what_you_missed ||
        coach?.context?.motifs?.length
    ) {
        return "thinking";
    }

    return "thinking";
}

class MagnusCoach {
    constructor(root) {
        this.root = root;
        this.image = root?.querySelector("[data-magnus-image]");
        this.status = root?.querySelector("[data-magnus-status]");
        this.messageBody = root?.parentElement?.querySelector(".magnus-coach-message-body");

        this.currentState = null;
        this.reactionTimer = null;
        this.talkTimer = null;

        if (!this.root || !this.image) {
            return;
        }

        this.root.classList.add("magnus-coach");

        this.image.addEventListener("load", () => {
            this.root.classList.add("magnus-ready");
        });
    }

    setState(state, coach = null) {
        if (!this.image) return;

        const nextState = coach
            ? magnusStateFromCoach(coach)
            : magnusNormalizeState(state);

        const config = MAGNUS_STATES[nextState];

        if (!config) return;

        const changed = nextState !== this.currentState;

        this.currentState = nextState;

        /*
         * Expression image.
         */
        this.image.src =
            `./assets/magnus/states/${config.image}`;

        this.image.alt =
            `Magnus coach — ${config.mood}`;

        this.root.dataset.state = nextState;
        this.root.dataset.mood = config.mood;
        this.root.dataset.reaction = config.reaction;

        if (this.status) {
            this.status.textContent = config.mood;
        }

        this.renderMessage(coach);

        if (changed) {
            this.react(config.reaction);
        }
    }

    renderMessage(coach = null) {
        if (!this.messageBody) return;

        this.messageBody.replaceChildren();

        const addText = (label, value, isHeadline = false) => {
            if (typeof value !== "string" || !value.trim()) return;

            const block = document.createElement("div");
            block.className = "magnus-coach-message-text";

            if (label) {
                const heading = document.createElement("strong");
                heading.textContent = `${label}: `;
                block.appendChild(heading);
            }

            block.appendChild(document.createTextNode(value.trim()));

            if (isHeadline) {
                block.style.marginBottom = "6px";
            }

            this.messageBody.appendChild(block);
        };

        if (!coach) {
            addText("", "Select a reviewed move to see detailed coaching.");
            return;
        }

        // 1. Standalone position mode (Free Board or Book Reader)
        if (coach?.context?.is_standalone) {
            addText("", coach.headline || "Position Coaching", true);
            if (coach.recommendation) {
                addText("Recommendation", coach.recommendation);
            }
            if (Array.isArray(coach.takeaways) && coach.takeaways.length) {
                addText("Positional factors", coach.takeaways.join("; "));
            }
            if (coach.positional?.source) {
                addText("Source", coach.positional.source);
            }
            return;
        }

        // 2. Move-by-move coaching mode
        const explanation = coach.explanation || {};
        const reasoning = coach.reasoning || {};
        const positional = coach.positional || {};

        addText("", explanation.headline || "");
        addText("", explanation.summary || "");
        addText("What you played", explanation.what_you_played);
        addText("Why it matters", explanation.why_it_is_wrong);
        addText("What you missed", explanation.what_you_missed);
        addText("Immediate effect", explanation.immediate_effect);
        addText("Better move", explanation.better_move);
        addText("Why it is better", explanation.why_better);
        addText("Long-term effect", explanation.longer_term_effect);
        addText("Lesson", explanation.lesson);
        addText("Reasoning", reasoning.primary_reason);

        // Positional insights from Eclipseth
        if (Array.isArray(positional.description) && positional.description.length) {
            addText("Positional insight", positional.description.slice(0, 2).join("; "));
        }
        if (positional.source) {
            addText("Positional source", positional.source);
        }

        if (!this.messageBody.childElementCount) {
            addText(
                "",
                "No detailed explanation is available for this move yet."
            );
        }
    }
    react(type = "nod") {
        if (!this.root) return;

        clearTimeout(this.reactionTimer);

        this.root.classList.remove(
            "magnus-reacting",
            "magnus-nod",
            "magnus-think",
            "magnus-question",
            "magnus-shock",
            "magnus-disappointed",
            "magnus-celebrate"
        );

        /*
         * Force animation restart.
         */
        void this.root.offsetWidth;

        this.root.classList.add("magnus-reacting");

        const className = {
            nod: "magnus-nod",
            think: "magnus-think",
            question: "magnus-question",
            shock: "magnus-shock",
            disappointed: "magnus-disappointed",
            celebrate: "magnus-celebrate"
        }[type] || "magnus-nod";

        this.root.classList.add(className);

        this.reactionTimer = setTimeout(() => {
            this.root.classList.remove(
                "magnus-reacting",
                className
            );
        }, 720);
    }

    talking(active = true) {
        if (!this.root) return;

        clearTimeout(this.talkTimer);

        this.root.classList.toggle(
            "magnus-talking",
            Boolean(active)
        );

        if (active) {
            this.talkTimer = setTimeout(() => {
                this.root.classList.remove("magnus-talking");
            }, 5000);
        }
    }

    reset() {
        clearTimeout(this.reactionTimer);
        clearTimeout(this.talkTimer);

        this.root?.classList.remove(
            "magnus-reacting",
            "magnus-talking",
            "magnus-nod",
            "magnus-think",
            "magnus-question",
            "magnus-shock",
            "magnus-disappointed",
            "magnus-celebrate"
        );

        this.currentState = null;
    }
}

window.MAGNUS_STATES = MAGNUS_STATES;
window.MagnusCoach = MagnusCoach;
window.magnusNormalizeState = magnusNormalizeState;
window.magnusStateFromCoach = magnusStateFromCoach;
