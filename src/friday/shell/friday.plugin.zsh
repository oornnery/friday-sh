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
    selected=$(friday session show --plain 2>/dev/null | fzf --height=40% --reverse --prompt="friday session> ")

    if [[ -n "$selected" ]]; then
        BUFFER="friday session resume $selected"
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
    friday model show | fzf --height=40% --reverse --prompt="model> "
}

# ─── Completions ──────────────────────────────────────────────────

_friday_completions() {
    local -a subcmds modes
    subcmds=(ask chat model mode session setting memory)
    modes=(auto code reader write debug)

    case "$words[2]" in
        ask|chat)
            _arguments \
                '--mode[Agent mode]:mode:(${modes})' \
                '--model[Model name]:model:' \
                '*:question:'
            ;;
        model)
            _arguments \
                '1:subcommand:(show)' \
                '2:model or provider: '
            ;;
        mode)
            _arguments \
                '1:subcommand:(show)' \
                '2:mode:(${modes})'
            ;;
        session)
            _arguments \
                '1:subcommand:(show resume new delete)' \
                '2:session id: '
            ;;
        setting)
            _arguments \
                '1:subcommand:(show)' \
                '2:key:(default_model fallback_model default_mode approval_policy max_steps)'
            ;;
        memory)
            _arguments \
                '1:subcommand:(show search add delete)' \
                '2:query or id: '
            ;;
        *)
            _describe 'command' subcmds
            ;;
    esac
}
compdef _friday_completions friday
