// SPDX-License-Identifier: Apache-2.0
// Ported from Kaldi (https://github.com/kaldi-asr/kaldi), Copyright the
// Kaldi authors, Apache License 2.0; translated to Rust and modified. See
// NOTICE.

//! Reading Kaldi's binary object format (files starting with "\0B"):
//! space-terminated tokens such as `<TransitionModel>`, integers and floats
//! each preceded by a byte giving their size, and matrices/vectors as a type
//! token ("FM", "DV", ...) followed by their dimensions and values.

use std::fmt;

#[derive(Debug)]
pub struct Error(pub String);

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl std::error::Error for Error {}

pub type Result<T> = std::result::Result<T, Error>;

/// A row-major matrix.
#[derive(Clone, Debug, PartialEq)]
pub struct Matrix {
    pub rows: usize,
    pub cols: usize,
    pub data: Vec<f64>,
}

impl Matrix {
    pub fn row(&self, i: usize) -> &[f64] {
        &self.data[i * self.cols..(i + 1) * self.cols]
    }
}

pub struct Reader<'a> {
    bytes: &'a [u8],
    position: usize,
}

impl<'a> Reader<'a> {
    /// A reader positioned after the binary-mode header "\0B".
    pub fn new(bytes: &'a [u8]) -> Result<Self> {
        if !bytes.starts_with(b"\0B") {
            return Err(Error("not a Kaldi binary file (no \\0B header)".into()));
        }
        Ok(Reader { bytes, position: 2 })
    }

    pub fn at_end(&self) -> bool {
        self.position >= self.bytes.len()
    }

    fn take(&mut self, count: usize) -> Result<&'a [u8]> {
        if self.position + count > self.bytes.len() {
            return Err(Error(format!("unexpected end of data at byte {}", self.position)));
        }
        let slice = &self.bytes[self.position..self.position + count];
        self.position += count;
        Ok(slice)
    }

    /// The next token, without its terminating space.
    pub fn token(&mut self) -> Result<String> {
        let start = self.position;
        while self.position < self.bytes.len() && self.bytes[self.position] != b' ' {
            self.position += 1;
        }
        let token = String::from_utf8_lossy(&self.bytes[start..self.position]).into_owned();
        self.position += 1; // the space
        Ok(token)
    }

    pub fn peek_token(&mut self) -> Result<String> {
        let saved = self.position;
        let token = self.token();
        self.position = saved;
        token
    }

    pub fn expect(&mut self, expected: &str) -> Result<()> {
        let token = self.token()?;
        if token != expected {
            return Err(Error(format!("expected {}, found {} at byte {}", expected, token, self.position)));
        }
        Ok(())
    }

    /// An integer: a size byte (negative for unsigned types), then the value.
    pub fn int(&mut self) -> Result<i64> {
        let size_byte = self.take(1)?[0] as i8;
        let b = self.take(size_byte.unsigned_abs() as usize)?;
        Ok(match size_byte {
            1 => b[0] as i8 as i64,
            -1 => b[0] as i64,
            2 => i16::from_le_bytes([b[0], b[1]]) as i64,
            -2 => u16::from_le_bytes([b[0], b[1]]) as i64,
            4 => i32::from_le_bytes(b.try_into().unwrap()) as i64,
            -4 => u32::from_le_bytes(b.try_into().unwrap()) as i64,
            8 | -8 => i64::from_le_bytes(b.try_into().unwrap()),
            _ => return Err(Error(format!("bad integer size {}", size_byte))),
        })
    }

    pub fn float(&mut self) -> Result<f64> {
        let size = self.take(1)?[0] as usize;
        let b = self.take(size)?;
        Ok(match size {
            4 => f32::from_le_bytes(b.try_into().unwrap()) as f64,
            8 => f64::from_le_bytes(b.try_into().unwrap()),
            _ => return Err(Error(format!("bad float size {}", size))),
        })
    }

    fn values(&mut self, count: usize, double: bool) -> Result<Vec<f64>> {
        let width = if double { 8 } else { 4 };
        let bytes = self.take(count * width)?;
        Ok(bytes
            .chunks_exact(width)
            .map(|c| if double { f64::from_le_bytes(c.try_into().unwrap()) } else { f32::from_le_bytes(c.try_into().unwrap()) as f64 })
            .collect())
    }

    /// A float or double matrix ("FM" / "DM").
    pub fn matrix(&mut self) -> Result<Matrix> {
        let double = match self.token()?.as_str() {
            "FM" => false,
            "DM" => true,
            other => return Err(Error(format!("expected a matrix, found {}", other))),
        };
        let rows = self.int()? as usize;
        let cols = self.int()? as usize;
        let data = self.values(rows * cols, double)?;
        Ok(Matrix { rows, cols, data })
    }

    /// A float or double vector ("FV" / "DV").
    pub fn vector(&mut self) -> Result<Vec<f64>> {
        let double = match self.token()?.as_str() {
            "FV" => false,
            "DV" => true,
            other => return Err(Error(format!("expected a vector, found {}", other))),
        };
        let size = self.int()? as usize;
        self.values(size, double)
    }

    /// A vector of integers: its length, then each value with its size byte.
    pub fn int_vector(&mut self) -> Result<Vec<i64>> {
        let size_of = self.take(1)?[0] as usize;
        let count = i32::from_le_bytes(self.take(4)?.try_into().unwrap()) as usize;
        (0..count)
            .map(|_| {
                let b = self.take(size_of)?;
                Ok(match size_of {
                    4 => i32::from_le_bytes(b.try_into().unwrap()) as i64,
                    _ => return Err(Error(format!("bad integer size {}", size_of))),
                })
            })
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_a_float_matrix() {
        let mut bytes = b"\0BFM ".to_vec();
        bytes.extend([4]);
        bytes.extend(2i32.to_le_bytes());
        bytes.extend([4]);
        bytes.extend(3i32.to_le_bytes());
        for v in [1.0f32, 2.0, 3.0, 4.0, 5.0, 6.0] {
            bytes.extend(v.to_le_bytes());
        }
        let m = Reader::new(&bytes).unwrap().matrix().unwrap();
        assert_eq!((m.rows, m.cols), (2, 3));
        assert_eq!(m.row(1), &[4.0, 5.0, 6.0]);
    }
}
