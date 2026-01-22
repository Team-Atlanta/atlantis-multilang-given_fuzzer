use serde::{Deserialize, Serialize};
use std::path::PathBuf;

use crate::common::utils;

#[derive(Serialize, Deserialize)]
pub struct InputGenClientConfig {
    harness_name: String,
    core_ids: Vec<usize>,
    input_gens: Option<Vec<String>>,
}

/// Check if a stage name is enabled in the config's input_gens list.
pub fn is_on_config(name: &String, config_path: &PathBuf, default: bool) -> bool {
    let config = utils::load_json::<InputGenClientConfig>(config_path)
        .unwrap_or_else(|e| panic!("Error in load_json: {}", e));
    if let Some(input_gens) = config.input_gens {
        input_gens.contains(name)
    } else {
        default
    }
}
