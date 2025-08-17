export interface CrosswordData {
    grid: string[][];
    filled_slots: { [key: string]: string };
    clues: { [key: string]: string };
    theme_entries: { [key: string]: string };
    slots?: Slot[];
    template_info?: {
        id: string;
        name: string;
        difficulty: string;
        description: string;
    };
}

export interface Slot {
    id: string;
    start: [number, number];
    direction: 'across' | 'down';
    length: number;
    cells: [number, number][];
}

export interface Template {
    id: string;
    name: string;
    size: [number, number];
    difficulty: 'easy' | 'medium' | 'hard';
    description: string;
}

export interface GenerateRequest {
    template?: string;
    theme?: string;
    themeEntry?: string;
    difficulty?: 'easy' | 'medium' | 'hard';
    clueType?: 'generate' | 'existing';
}
