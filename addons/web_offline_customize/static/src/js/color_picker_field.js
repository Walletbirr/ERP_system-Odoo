/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, useState } from "@odoo/owl";

class ColorPickerField extends Component {
    static template = "web_offline_customize.ColorPickerField";
    static props = { ...standardFieldProps };

    setup() {
        this.state = useState({
            value: this.props.record.data[this.props.name] || "#714B67",
        });
    }

    get displayValue() {
        return this.props.record.data[this.props.name] || "#714B67";
    }

    onColorChange(ev) {
        const value = ev.target.value;
        this.state.value = value;
        this.props.record.update({ [this.props.name]: value });
    }

    onTextChange(ev) {
        const value = ev.target.value;
        this.state.value = value;
        this.props.record.update({ [this.props.name]: value });
    }
}

export const colorPickerField = {
    component: ColorPickerField,
    supportedTypes: ["char"],
};

registry.category("fields").add("offline_color_picker", colorPickerField);
