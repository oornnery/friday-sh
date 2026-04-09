# friday.plugin.zsh — ZSH integration for Friday agent
#
# Installation:
#   source /path/to/friday.plugin.zsh
#   Or symlink into ~/.oh-my-zsh/custom/plugins/friday/
#
# Requires: friday CLI in PATH, fzf (optional, for fuzzy features)

# ─── Shorthand ────────────────────────────────────────────────────

f() {
    friday ask "$*"
}

# ─── Shell state hooks ────────────────────────────────────────────

# Capture last command and exit code for Friday's RuntimeContext
__friday_preexec() {
    export FRIDAY_LAST_CMD="$1"
}

__friday_precmd() {
    export FRIDAY_LAST_EXIT=$?
}

# Register hooks (avoid duplicates)
if [[ -z "$__FRIDAY_HOOKS_REGISTERED" ]]; then
    autoload -Uz add-zsh-hook
    add-zsh-hook preexec __friday_preexec
    add-zsh-hook precmd __friday_precmd
    __FRIDAY_HOOKS_REGISTERED=1
fi

# ─── Ctrl+F: Ask Friday about current buffer ─────────────────────

__friday_ask_widget() {
    local current_buffer="$BUFFER"
    local last_cmd="${FRIDAY_LAST_CMD:-}"
    local last_exit="${FRIDAY_LAST_EXIT:-0}"

    local context=""
    [[ -n "$last_cmd" ]] && context="Last command: $last_cmd (exit $last_exit)\n"
    [[ -n "$current_buffer" ]] && context="${context}Current line: $current_buffer\n"

    if [[ -z "$context" ]]; then
        zle -M "friday: nothing to ask about"
        return
    fi

    local result
    result=$(echo -e "$context" | friday ask "What should I do?" --mode code 2>/dev/null)

    if [[ -n "$result" ]]; then
        BUFFER="$result"
        CURSOR=${#BUFFER}
    fi
    zle redisplay
}
zle -N __friday_ask_widget
bindkey '^F' __friday_ask_widget

# ─── fzf integration ─────────────────────────────────────────────

# Ctrl+G: Fuzzy pick a saved Friday session
__friday_fzf_sessions() {
    if ! command -v fzf &>/dev/null; then
        zle -M "friday: fzf not installed"
        return
    fi

    local selected
    selected=$(friday sessions list --plain 2>/dev/null | fzf --height=40% --reverse --prompt="friday session> ")

    if [[ -n "$selected" ]]; then
        BUFFER="friday sessions set $selected"
        CURSOR=${#BUFFER}
    fi
    zle redisplay
}
zle -N __friday_fzf_sessions
bindkey '^G' __friday_fzf_sessions

# fzf model selector
friday-select-model() {
    if ! command -v fzf &>/dev/null; then
        echo "fzf not installed" >&2
        return 1
    fi
    friday models list | fzf --height=40% --reverse --prompt="model> "
}

# ─── Completions ──────────────────────────────────────────────────

_friday_completions() {
    local -a subcmds modes model_subcmds mode_subcmds session_subcmds settings_subcmds memory_subcmds
    subcmds=(ask chat models modes sessions settings memories)
    modes=(auto code reader write debug)
    model_subcmds=(list set)
    mode_subcmds=(list set)
    session_subcmds=(list set delete new)
    settings_subcmds=(list get)
    memory_subcmds=(list search set get delete)

    case "$words[2]" in
        ask|chat)
            _arguments \
                '--mode[Agent mode]:mode:(${modes})' \
                '--model[Model name]:model:' \
                '*:question:'
            ;;
        models)
            _arguments \
                '1:subcommand:(${model_subcmds})' \
                '2:model or provider: '
            ;;
        modes)
            _arguments \
                '1:subcommand:(${mode_subcmds})' \
                '2:mode:(${modes})'
            ;;
        sessions)
            _arguments \
                '1:subcommand:(${session_subcmds})' \
                '2:session id: '
            ;;
        settings)
            _arguments \
                '1:subcommand:(${settings_subcmds})' \
                '2:key:(default_model fallback_model zai_api_key zai_base_url default_mode approval_policy max_steps session_dir config_dir memory_db_path memory_top_k memory_auto_promote mcp_servers)'
            ;;
        memories)
            _arguments \
                '1:subcommand:(${memory_subcmds})' \
                '2:value: '
            ;;
        *)
            _describe 'command' subcmds
            ;;
    esac
}
compdef _friday_completions friday
