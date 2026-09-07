/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component } from "@odoo/owl";

const WEEKDAY_LABELS = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];
const MONTH_LABELS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
];

export class AttendanceCalendarField extends Component {
    static template = "binget_attendance.AttendanceCalendarField";
    static props = { ...standardFieldProps };

    get weekdayLabels() {
        return WEEKDAY_LABELS;
    }

    get year() {
        return parseInt(this.props.record.data.year, 10) || new Date().getFullYear();
    }

    get month() {
        return parseInt(this.props.record.data.month, 10) || new Date().getMonth() + 1;
    }

    get monthLabel() {
        return MONTH_LABELS[this.month - 1];
    }

    get selectedDates() {
        const raw = this.props.record.data[this.props.name];
        if (!raw) {
            return [];
        }
        try {
            const parsed = JSON.parse(raw);
            return Array.isArray(parsed) ? parsed : [];
        } catch {
            return [];
        }
    }

    get selectedCount() {
        return this.selectedDates.length;
    }

    get daysInMonth() {
        return new Date(this.year, this.month, 0).getDate();
    }

    get leadingBlanks() {
        return new Date(this.year, this.month - 1, 1).getDay();
    }

    isoDate(day) {
        const mm = String(this.month).padStart(2, "0");
        const dd = String(day).padStart(2, "0");
        return `${this.year}-${mm}-${dd}`;
    }

    get calendarCells() {
        const cells = [];
        for (let i = 0; i < this.leadingBlanks; i++) {
            cells.push({ blank: true, key: `blank-${i}` });
        }
        const selected = new Set(this.selectedDates);
        for (let day = 1; day <= this.daysInMonth; day++) {
            const iso = this.isoDate(day);
            cells.push({
                blank: false,
                day,
                iso,
                key: iso,
                selected: selected.has(iso),
            });
        }
        return cells;
    }

    onCellClick(cell) {
        if (this.props.readonly || cell.blank) {
            return;
        }
        const dates = new Set(this.selectedDates);
        if (dates.has(cell.iso)) {
            dates.delete(cell.iso);
        } else {
            dates.add(cell.iso);
        }
        const sorted = Array.from(dates).sort();
        this.props.record.update({ [this.props.name]: JSON.stringify(sorted) });
    }

    onClearAll() {
        if (this.props.readonly || !this.selectedCount) {
            return;
        }
        this.props.record.update({ [this.props.name]: JSON.stringify([]) });
    }
}

registry.category("fields").add("attendance_calendar", {
    component: AttendanceCalendarField,
    supportedTypes: ["text", "char"],
});
